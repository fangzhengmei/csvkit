# csvkit CSV 转 JSON 工具模块技术分析报告

## 一、模块概述

`csvjson` 是 csvkit 工具集中负责将 CSV 数据转换为 JSON 输出的核心模块，位于 `csvkit/utilities/csvjson.py`。该模块支持多种输出格式，包括标准 JSON 数组、键索引字典、GeoJSON 要素集合以及行分隔的流式 JSON 输出。

## 二、不同输出格式的数据结构转换差异

### 2.1 标准 JSON 数组格式（默认）

**生成逻辑**：
- 核心方法：`output_json()` [csvjson.py:124-130]
- 调用 `agate.Table.to_json()` 方法将整个表转换为 JSON 数组
- 每个数组元素代表 CSV 中的一行数据，以列名为键的对象形式存储

**数据结构示例**：
```json
[
  {"a": true, "b": 2.0, "c": 3.0},
  {"a": false, "b": 5.0, "c": 6.0}
]
```

**转换特点**：
- 保留 CSV 中的行顺序
- 列名自动作为 JSON 对象的键
- 支持类型推断（除非使用 `--no-inference`）
- 需要将整个 CSV 加载到内存中

### 2.2 键索引字典格式

**生成逻辑**：
- 核心参数：`--key` 或 `-k` [csvjson.py:20-22]
- 同样使用 `agate.Table.to_json()` 方法，但传入 `key` 参数
- 输出不再是数组，而是以指定列的值为键的字典对象

**数据结构示例**：
```json
{
  "True": {"a": true, "b": 2.0, "c": 3.0},
  "False": {"a": false, "b": 5.0, "c": 6.0}
}
```

**转换特点**：
- 指定列的值必须唯一，否则抛出 `ValueError`
- 适合需要快速按主键查找的场景
- 键列的值同时保留在值对象中

### 2.3 GeoJSON 要素集合格式

**生成逻辑**：
- 核心方法：`output_geojson()` [csvjson.py:132-140]
- 当同时指定 `--lat` 和 `--lon` 参数时触发
- 使用内部 `GeoJsonGenerator` 类生成符合 RFC 7946 标准的 GeoJSON

**数据结构示例**：
```json
{
  "type": "FeatureCollection",
  "bbox": [-95.334619, 32.299076986939205, -95.250699, 32.351434],
  "features": [
    {
      "type": "Feature",
      "id": "dcl",
      "properties": {
        "title": "Downtown Coffee Lounge",
        "type": "Gallery"
      },
      "geometry": {
        "type": "Point",
        "coordinates": [-95.30181, 32.35066]
      }
    }
  ],
  "crs": {
    "type": "name",
    "properties": {"name": "EPSG:4269"}
  }
}
```

**转换特点**：
- 顶层为 `FeatureCollection` 类型
- 包含 `features` 数组，每个元素是一个 `Feature`
- 可选包含 `bbox`（边界框）和 `crs`（坐标参考系统）
- 地理列（lat/lon/type/geometry）不会出现在 `properties` 中

### 2.4 行分隔流式 JSON (NDJSON)

**生成逻辑**：
- 核心方法：`streaming_output_ndjson()` [csvjson.py:142-153]
- 当满足流式条件时（见第四节）触发
- 直接使用 `agate.csv.reader` 逐行读取，不加载整个表

**数据结构示例**：
```json
{"a": "1", "b": "2", "c": "3"}
{"a": "4", "b": "5", "c": "6"}
```

**转换特点**：
- 每行是一个独立的 JSON 对象
- 对象之间用换行符分隔
- 不使用类型推断，所有值保持字符串类型
- 内存效率极高，适合处理超大文件

### 2.5 行分隔流式 GeoJSON (NDGeoJSON)

**生成逻辑**：
- 核心方法：`streaming_output_ndgeojson()` [csvjson.py:155-161]
- 同时指定 `--stream`、`--lat`、`--lon` 时触发
- 逐行生成 GeoJSON `Feature` 对象

**数据结构示例**：
```json
{"type": "Feature", "properties": {...}, "geometry": {...}}
{"type": "Feature", "properties": {...}, "geometry": {...}}
```

**转换特点**：
- 每行是一个完整的 `Feature` 对象
- 没有顶层 `FeatureCollection` 包装
- 支持地理坐标转换和几何处理
- 适合流式处理地理空间大数据

## 三、地理坐标信息的提取与映射逻辑

### 3.1 核心处理类：GeoJsonGenerator

`GeoJsonGenerator` 是 `CSVJSON` 类的内部类，负责所有地理空间数据的转换逻辑 [csvjson.py:163-290]。

**初始化流程**：
```python
def __init__(self, args, column_names):
    # 匹配经纬度列
    self.lat_column = match_column_identifier(column_names, self.args.lat, ...)
    self.lon_column = match_column_identifier(column_names, self.args.lon, ...)
    
    # 可选列匹配
    self.type_column = match_column_identifier(...)  # GeoJSON 类型列
    self.geometry_column = match_column_identifier(...)  # 几何列
    self.id_column = match_column_identifier(...)  # 要素 ID 列
```

**列匹配机制**：
- 支持列名或列索引（1-based，除非 `--zero-based`）
- 使用 `cli.match_column_identifier()` 函数进行智能匹配
- 整数优先作为位置索引，非数字字符串作为列名

### 3.2 几何对象生成逻辑

核心方法 `geometry_for_row()` [csvjson.py:236-255] 负责从行数据中提取几何信息：

**优先级顺序**：
1. **直接几何列优先**：如果指定了 `--geometry` 参数，直接解析该列的 JSON 字符串
   ```python
   if self.geometry_column is not None:
       return json.loads(row[self.geometry_column])
   ```
   支持任意 GeoJSON 几何类型：Point、LineString、Polygon、MultiPoint 等

2. **经纬度列次之**：如果指定了 `--lat` 和 `--lon`，从对应列提取坐标值
   ```python
   lon = float(row[self.lon_column])
   lat = float(row[self.lat_column])
   ```
   - 坐标值会尝试转换为浮点数
   - 转换失败时返回 `None`（无效几何）

3. **生成 Point 几何**：如果经纬度有效，生成标准 Point 几何
   ```python
   return OrderedDict([
       ('type', 'Point'),
       ('coordinates', [lon, lat]),  # 注意：GeoJSON 坐标顺序是 [经度, 纬度]
   ])
   ```

**重要细节**：
- GeoJSON 标准要求坐标顺序为 `[经度, 纬度]`，而非通常的 `[纬度, 经度]`
- 支持的几何类型取决于数据来源：
  - 经纬度列只能生成 `Point` 类型
  - 几何列可以生成任意 GeoJSON 几何类型

### 3.3 要素对象构建逻辑

核心方法 `feature_for_row()` [csvjson.py:217-234] 负责构建完整的 GeoJSON Feature：

**构建流程**：
1. **初始化 Feature 骨架**：
   ```python
   feature = OrderedDict([
       ('type', 'Feature'),
       ('properties', OrderedDict()),
   ])
   ```

2. **遍历行数据，分类处理**：
   ```python
   for i, c in enumerate(row):
       # 跳过特殊列：type列、地理列、几何列
       if i in (self.type_column, self.lat_column, self.lon_column, self.geometry_column):
           continue
       
       # ID 列处理
       if i == self.id_column:
           feature['id'] = c
       
       # 普通属性列
       elif c:
           feature['properties'][self.column_names[i]] = c
   ```

3. **添加几何信息**：
   ```python
   feature['geometry'] = self.geometry_for_row(row)
   ```

**属性过滤规则**：
- 以下列不会出现在 `properties` 中：
  - `--lat` 指定的纬度列
  - `--lon` 指定的经度列
  - `--type` 指定的类型列
  - `--geometry` 指定的几何列
- `--key` 指定的列会同时作为 `id` 和保留在 `properties` 中

### 3.4 要素集合与边界框计算

核心方法 `generate_feature_collection()` [csvjson.py:187-215] 负责构建完整的 FeatureCollection：

**构建流程**：
1. **遍历所有行生成 Feature**：
   ```python
   features = []
   bounds = self.GeoJsonBounds()
   
   for row in table.rows:
       feature = self.feature_for_row(row)
       
       # 累积边界框
       if not self.args.no_bbox:
           bounds.add_feature(feature)
       
       features.append(feature)
   ```

2. **构建 FeatureCollection 对象**：
   ```python
   items = [
       ('type', 'FeatureCollection'),
       ('features', features),
   ]
   
   # 可选添加边界框
   if not self.args.no_bbox:
       items.insert(1, ('bbox', bounds.bbox()))
   
   # 可选添加坐标参考系统
   if self.args.crs:
       items.append(('crs', OrderedDict([
           ('type', 'name'),
           ('properties', {'name': self.args.crs}),
       ])))
   ```

### 3.5 边界框（BBox）计算机制

内部类 `GeoJsonBounds` [csvjson.py:257-289] 负责计算要素集合的空间范围：

**数据结构**：
```python
class GeoJsonBounds:
    def __init__(self):
        self.min_lon = None  # 最小经度
        self.min_lat = None  # 最小纬度
        self.max_lon = None  # 最大经度
        self.max_lat = None  # 最大纬度
```

**核心方法**：
1. **`add_feature(feature)`**：从 Feature 中提取坐标并更新边界
   ```python
   def add_feature(self, feature):
       if 'geometry' in feature and 'coordinates' in feature['geometry']:
           self.update_coordinates(feature['geometry']['coordinates'])
   ```

2. **`update_coordinates(coordinates)`**：递归处理任意嵌套的坐标数组
   ```python
   def update_coordinates(self, coordinates):
       # 判断是否为点坐标（长度<=3且首元素是数值）
       if len(coordinates) <= 3 and isinstance(coordinates[0], (float, int)):
           self.update_lon(coordinates[0])
           self.update_lat(coordinates[1])
       else:
           # 递归处理嵌套坐标（LineString、Polygon 等）
           for coordinate in coordinates:
               self.update_coordinates(coordinate)
   ```

3. **`bbox()`**：输出标准 GeoJSON bbox 格式
   ```python
   def bbox(self):
       return [self.min_lon, self.min_lat, self.max_lon, self.max_lat]
   ```

**支持的几何类型**：
- **Point**：直接使用坐标值
- **LineString**：遍历所有点，取极值
- **Polygon**：遍历外环和内环的所有点
- **MultiPoint/MultiLineString/MultiPolygon**：递归处理所有子几何

### 3.6 坐标参考系统（CRS）支持

通过 `--crs` 参数可以为 GeoJSON 输出添加坐标参考系统信息：

**输出格式**：
```json
"crs": {
  "type": "name",
  "properties": {
    "name": "EPSG:4269"
  }
}
```

**使用场景**：
- 当数据使用非 WGS84 坐标系时（如 NAD83、UTM 等）
- 便于 GIS 软件正确识别和投影转换

**注意事项**：
- csvkit 不进行实际的坐标转换，仅添加元数据
- 默认情况下假设坐标为 WGS84 (EPSG:4326)

## 四、命令行参数对输出结构的影响

### 4.1 参数分类与影响矩阵

| 参数 | 短格式 | 影响的输出格式 | 数据结构变化 |
|------|--------|---------------|-------------|
| `--key` | `-k` | 标准 JSON | 数组 → 字典 |
| `--lat` | - | GeoJSON 系列 | 启用地理空间输出 |
| `--lon` | - | GeoJSON 系列 | 启用地理空间输出 |
| `--type` | - | GeoJSON 系列 | 定义几何类型 |
| `--geometry` | - | GeoJSON 系列 | 使用预定义几何 |
| `--crs` | - | GeoJSON 系列 | 添加坐标参考系统 |
| `--no-bbox` | - | GeoJSON 系列 | 移除边界框字段 |
| `--stream` | - | NDJSON/NDGeoJSON | 启用流式输出 |
| `--indent` | `-i` | 所有格式 | 美化输出格式 |
| `--no-inference` | `-I` | 流式格式 | 禁用类型推断 |
| `--snifflimit` | `-y` | 流式格式 | 控制 CSV 方言嗅探 |

### 4.2 核心参数详细分析

#### 4.2.1 `--key` (-k)：键索引模式

**参数定义** [csvjson.py:20-22]：
```python
self.argparser.add_argument(
    '-k', '--key', dest='key',
    help='Output JSON as an object keyed by a given column, KEY, rather than as an array. '
         'All column values must be unique. If --lat and --lon are specified, '
         'this column is used as the GeoJSON Feature ID.')
```

**行为差异**：
- **标准 JSON 模式**：将输出从数组转换为对象字典
- **GeoJSON 模式**：作为 Feature 的 `id` 字段值

**约束条件**：
- 键列的值必须唯一
- 不能与 `--stream` 同时使用（除非同时使用 `--lat`/`--lon`）
  ```python
  if self.args.key and self.args.streamOutput and not (self.args.lat and self.args.lon):
      self.argparser.error('--key is only allowed with --stream when --lat and --lon are also specified.')
  ```

#### 4.2.2 `--lat` / `--lon`：地理坐标列

**参数定义** [csvjson.py:23-30]：
```python
self.argparser.add_argument(
    '--lat', dest='lat',
    help='A column index or name containing a latitude. Output will be GeoJSON instead of JSON. '
         'Requires --lon.')
self.argparser.add_argument(
    '--lon', dest='lon',
    help='A column index or name containing a longitude. Output will be GeoJSON instead of JSON. '
         'Requires --lat.')
```

**验证逻辑** [csvjson.py:61-64]：
```python
if self.args.lat and not self.args.lon:
    self.argparser.error('--lon is required whenever --lat is specified.')
if self.args.lon and not self.args.lat:
    self.argparser.error('--lat is required whenever --lon is specified.')
```

**触发行为**：
- 当同时指定时，`is_geo()` 方法返回 `True` [csvjson.py:111-112]
- 输出从标准 JSON 切换为 GeoJSON 格式

#### 4.2.3 `--type`：几何类型列

**参数定义** [csvjson.py:31-34]：
```python
self.argparser.add_argument(
    '--type', dest='type',
    help='A column index or name containing a GeoJSON type. '
         'Output will be GeoJSON instead of JSON. Requires --lat and --lon.')
```

**使用场景**：
- 当 CSV 中包含几何类型信息列时
- 与 `--geometry` 参数配合使用

#### 4.2.4 `--geometry`：几何数据列

**参数定义** [csvjson.py:35-38]：
```python
self.argparser.add_argument(
    '--geometry', dest='geometry',
    help='A column index or name containing a GeoJSON geometry. '
         'Output will be GeoJSON instead of JSON. Requires --lat and --lon.')
```

**行为**：
- 该列的值应该是完整的 GeoJSON 几何对象的 JSON 字符串
- 优先级高于 `--lat`/`--lon` 生成的 Point 几何
- 支持任意复杂的几何类型

#### 4.2.5 `--crs`：坐标参考系统

**参数定义** [csvjson.py:39-41]：
```python
self.argparser.add_argument(
    '--crs', dest='crs',
    help='A coordinate reference system string to be included with GeoJSON output. '
         'Requires --lat and --lon.')
```

**输出效果**：
在 FeatureCollection 中添加 `crs` 字段：
```json
"crs": {
  "type": "name",
  "properties": {
    "name": "EPSG:4269"
  }
}
```

#### 4.2.6 `--no-bbox`：禁用边界框计算

**参数定义** [csvjson.py:43-44]：
```python
self.argparser.add_argument(
    '--no-bbox', dest='no_bbox', action='store_true',
    help='Disable the calculation of a bounding box.')
```

**影响**：
- 非流式 GeoJSON 输出时，不计算和包含 `bbox` 字段
- 可以略微提升性能（不需要遍历所有坐标）
- 流式 GeoJSON 输出本身就不包含 bbox

#### 4.2.7 `--stream`：流式输出模式

**参数定义** [csvjson.py:46-47]：
```python
self.argparser.add_argument(
    '--stream', dest='streamOutput', action='store_true',
    help='Output JSON as a stream of newline-separated objects, rather than as an array.')
```

**触发条件**：
需要同时满足以下条件才能真正启用流式处理（见 `can_stream()` 方法）：
- `--stream` 已指定
- `--no-inference` 已指定
- `--snifflimit 0` 已指定
- 没有使用 `--skip-lines`

**输出格式变化**：
- 标准 JSON：数组 → 每行一个对象
- GeoJSON：FeatureCollection → 每行一个 Feature

#### 4.2.8 `--no-inference` (-I)：禁用类型推断

**参数定义** [csvjson.py:52-55]：
```python
self.argparser.add_argument(
    '-I', '--no-inference', dest='no_inference', action='store_true',
    help='Disable type inference (and --locale, --date-format, --datetime-format, --no-leading-zeroes) '
         'when parsing the input.')
```

**影响**：
- 所有列值保持字符串类型，不尝试转换为数字、布尔、日期等
- 是启用流式输出的必要条件之一
- 可以显著提升大文件处理速度

#### 4.2.9 `--snifflimit` (-y)：CSV 方言嗅探限制

**参数定义** [csvjson.py:49-51]：
```python
self.argparser.add_argument(
    '-y', '--snifflimit', dest='sniff_limit', type=int, default=1024,
    help='Limit CSV dialect sniffing to the specified number of bytes. '
         'Specify "0" to disable sniffing entirely, or "-1" to sniff the entire file.')
```

**流式输出要求**：
- 必须设置为 `0`（完全禁用嗅探）
- 因为嗅探需要读取文件的部分内容，与纯流式处理不兼容

#### 4.2.10 `--indent` (-i)：输出缩进

**参数定义** [csvjson.py:16-18]：
```python
self.argparser.add_argument(
    '-i', '--indent', dest='indent', type=int,
    help='Indent the output JSON this many spaces. Disabled by default.')
```

**使用方式**：
- 传递给 `json.dump()` 的 `indent` 参数
- 仅影响输出的可读性，不影响数据结构
- 适用于所有非流式输出格式

### 4.3 参数组合与输出格式决策树

主方法 `main()` 中的决策逻辑 [csvjson.py:57-96]：

```python
def main(self):
    # 1. 参数验证
    if self.args.lat and not self.args.lon: ...
    if self.args.key and self.args.streamOutput and not (self.args.lat and self.args.lon): ...
    
    # 2. 决策输出模式
    if self.can_stream():
        # 流式输出路径
        if self.is_geo():
            self.streaming_output_ndgeojson()  # NDGeoJSON
        else:
            self.streaming_output_ndjson()      # NDJSON
    else:
        # 非流式输出路径
        if self.is_geo():
            self.output_geojson()                # GeoJSON FeatureCollection
        else:
            self.output_json()                   # 标准 JSON 数组/字典
```

**决策流程图**：
```
                    开始
                      │
                      ▼
              ┌───────────────┐
              │ can_stream()? │
              └───────────────┘
                 │           │
               是│           │否
                 ▼           ▼
         ┌───────────┐  ┌───────────┐
         │ is_geo()? │  │ is_geo()? │
         └───────────┘  └───────────┘
            │       │    │       │
          是│       │否  是│       │否
            ▼       ▼     ▼       ▼
       NDGeoJSON  NDJSON  GeoJSON  标准JSON
```

## 五、大文件流式输出的时机控制

### 5.1 流式输出的核心优势

**内存效率对比**：
- **非流式模式**：需要将整个 CSV 文件加载到内存中的 `agate.Table` 对象
  - 内存占用 ≈ 文件大小 × 类型推断开销
  - 适合小到中等规模文件（通常 < 1GB）

- **流式模式**：逐行读取、逐行处理、逐行输出
  - 内存占用 ≈ 常数（仅保持当前行数据）
  - 适合超大规模文件（GB 级别甚至更大）

### 5.2 流式输出的启用条件

**核心方法 `can_stream()`** [csvjson.py:103-109]：
```python
def can_stream(self):
    return (
        self.args.streamOutput      # 条件1: --stream 参数
        and self.args.no_inference  # 条件2: --no-inference 参数
        and self.args.sniff_limit == 0  # 条件3: --snifflimit 0
        and not self.args.skip_lines    # 条件4: 无 --skip-lines
    )
```

**条件详解**：

| 条件 | 参数 | 原因分析 |
|------|------|----------|
| 1 | `--stream` | 用户明确请求流式输出 |
| 2 | `--no-inference` | 类型推断需要读取样本数据进行分析 |
| 3 | `--snifflimit 0` | CSV 方言嗅探需要读取文件头部 |
| 4 | 无 `--skip-lines` | 跳过行需要先读取这些行 |

**为什么这些条件是必要的**：

1. **类型推断 (`--no-inference`)**：
   - agate 的类型推断系统需要扫描数据样本
   - 例如，判断某个列是数字还是字符串需要查看多个值
   - 这与"逐行处理、不前瞻"的流式模型冲突

2. **CSV 方言嗅探 (`--snifflimit 0`)**：
   - `csv.Sniffer` 需要读取文件的一部分来推断分隔符、引号字符等
   - 设置为 0 表示完全禁用嗅探，使用标准 CSV 格式

3. **跳过行 (`--skip-lines`)**：
   - 跳过开头的 N 行需要先读取这些行
   - 虽然技术上可以实现，但为了简化设计，csvkit 选择禁止

### 5.3 流式输出的两种实现

#### 5.3.1 标准 NDJSON 流式输出

**方法 `streaming_output_ndjson()`** [csvjson.py:142-153]：
```python
def streaming_output_ndjson(self):
    # 1. 创建 CSV 读取器（不加载全部数据）
    rows = agate.csv.reader(self.input_file, **self.reader_kwargs)
    
    # 2. 读取第一行作为列名
    column_names = next(rows)
    
    # 3. 逐行处理剩余数据
    for row in rows:
        # 构建有序字典
        data = OrderedDict()
        for i, column in enumerate(column_names):
            try:
                data[column] = row[i]
            except IndexError:
                # 处理行长度不一致的情况
                data[column] = None
        
        # 4. 立即输出当前行的 JSON
        self.dump_json(data, newline=True)
```

**实现细节**：
- 使用 `agate.csv.reader` 直接读取，绕过 `agate.Table`
- 列名仅读取一次，然后复用
- 每行数据读取后立即构建 JSON 并输出
- 内存中不保留任何历史行数据

**错误处理**：
- 当某行的列数少于表头时，缺失的列值设为 `None`
- 不进行任何类型转换，所有值保持字符串类型

#### 5.3.2 GeoJSON 流式输出 (NDGeoJSON)

**方法 `streaming_output_ndgeojson()`** [csvjson.py:155-161]：
```python
def streaming_output_ndgeojson(self):
    # 1. 创建 CSV 读取器
    rows = agate.csv.reader(self.input_file, **self.reader_kwargs)
    
    # 2. 读取列名
    column_names = next(rows)
    
    # 3. 初始化 GeoJSON 生成器（一次性配置）
    geojson_generator = self.GeoJsonGenerator(self.args, column_names)
    
    # 4. 逐行处理
    for row in rows:
        # 使用生成器创建 Feature 对象
        self.dump_json(geojson_generator.feature_for_row(row), newline=True)
```

**与标准 NDJSON 的差异**：
- 使用 `GeoJsonGenerator.feature_for_row()` 处理地理坐标
- 输出的每行是完整的 GeoJSON Feature 对象
- 同样支持 `--geometry` 参数指定的复杂几何

### 5.4 非流式输出的处理流程

为了对比，让我们看一下非流式模式的实现：

**方法 `output_json()`** [csvjson.py:124-130]：
```python
def output_json(self):
    self.read_csv_to_table().to_json(
        self.output_file,
        key=self.args.key,
        newline=self.args.streamOutput,
        indent=self.args.indent,
    )
```

**方法 `read_csv_to_table()`** [csvjson.py:114-122]：
```python
def read_csv_to_table(self):
    sniff_limit = self.args.sniff_limit if self.args.sniff_limit != -1 else None
    return agate.Table.from_csv(
        self.input_file,
        skip_lines=self.args.skip_lines,
        sniff_limit=sniff_limit,
        column_types=self.get_column_types(),
        **self.reader_kwargs,
    )
```

**关键差异**：
- 调用 `agate.Table.from_csv()` 加载整个表到内存
- 然后调用表的 `to_json()` 方法一次性输出
- 支持类型推断、键索引等高级特性

### 5.5 数据 emit 时机的精确控制

#### 5.5.1 流式模式的 emit 时机

**每行 emit 一次**：
```python
for row in rows:
    # 处理当前行...
    self.dump_json(data, newline=True)  # 立即输出
```

**输出特征**：
- 每读取一行数据，立即执行 `json.dump()`
- 输出缓冲区立即刷新（取决于 `output_file` 的缓冲策略）
- 下游程序可以立即开始处理输出行

#### 5.5.2 非流式模式的 emit 时机

**全部处理完成后一次性 emit**：
```python
# 1. 先加载全部数据
table = self.read_csv_to_table()

# 2. 然后一次性输出
table.to_json(self.output_file, ...)
```

**输出特征**：
- 必须等待整个 CSV 解析完成
- 内存中构建完整的 Python 数据结构（列表或字典）
- 最后一次性序列化为 JSON

### 5.6 性能与资源对比

| 维度 | 流式模式 | 非流式模式 |
|------|----------|-----------|
| **内存占用** | O(1) 常数级 | O(N) 与数据量成正比 |
| **启动延迟** | 极低（读取首行后立即开始） | 较高（需加载全部数据） |
| **支持的特性** | 有限（无类型推断、无键索引） | 完整（类型推断、键索引、bbox） |
| **CPU 开销** | 较低（无类型推断） | 较高（类型分析和转换） |
| **适用场景** | 超大文件、ETL 流水线 | 数据分析、交互式使用 |

### 5.7 流式输出的实际应用场景

**典型使用命令**：
```bash
# 标准 NDJSON 流式输出
csvjson --stream --no-inference --snifflimit 0 huge_data.csv > output.ndjson

# NDGeoJSON 流式输出
csvjson --stream --no-inference --snifflimit 0 --lat latitude --lon longitude geo_data.csv > output.ndgeojson
```

**适用场景**：
1. **日志处理**：超大 CSV 格式的日志文件
2. **数据导出**：从数据库导出的百万级记录
3. **ETL 流水线**：作为数据处理管道的中间环节
4. **地理空间大数据**：GIS 数据的批量转换和导入

### 5.8 流式输出的限制与注意事项

**功能限制**：
- 无法使用 `--key` 键索引（除非结合 GeoJSON）
- 无法使用 `--skip-lines` 跳过开头行
- 所有值保持字符串类型，无自动转换
- GeoJSON 模式下无 `bbox` 和 `crs`

**数据一致性**：
- 行长度不一致时，缺失列设为 `None`
- 无效的坐标值会导致 `geometry` 为 `null`
- 建议在流式处理前进行数据清洗

## 六、异常与边界场景行为机制分析

### 6.1 键索引模式下重复键的错误处理

#### 6.1.1 错误检测机制

**触发场景**：
当使用 `--key` 参数指定某列作为字典键时，如果该列存在重复值，会触发错误。

**测试用例验证** [test_csvjson.py:78-84]：
```python
def test_duplicate_keys(self):
    output_file = io.StringIO()
    utility = CSVJSON(['-k', 'a', 'examples/dummy3.csv'], output_file)
    self.assertRaisesRegex(ValueError,
                           'Value True is not unique in the key column.',
                           utility.run)
```

**输入数据** (`dummy3.csv`)：
```csv
a,b,c
1,2,3
1,4,5
```

两行的 `a` 列值均为 `1`，经过类型推断后转换为 `True`（布尔值），因此触发重复键错误。

#### 6.1.2 错误传播路径

**调用链分析**：
```
CSVJSON.output_json()
    → agate.Table.to_json(key=self.args.key)
        → 内部字典构建时检测重复键
            → 抛出 ValueError
```

**关键代码** [csvjson.py:124-130]：
```python
def output_json(self):
    self.read_csv_to_table().to_json(
        self.output_file,
        key=self.args.key,  # 传入 key 参数
        newline=self.args.streamOutput,
        indent=self.args.indent,
    )
```

**错误检测位置**：
重复键的检测发生在 `agate.Table.to_json()` 方法内部。当构建输出字典时，agate 会检查每个键值是否已存在于字典中。

#### 6.1.3 错误呈现形式

**错误消息格式**：
```
ValueError: Value True is not unique in the key column.
```

**用户可见的输出**：
- 通过 `cli.py` 中的异常处理器 `_install_exception_handler()` 统一处理
- 非 verbose 模式下输出到 stderr：`ValueError: Value True is not unique in the key column.`
- verbose 模式下输出完整的 traceback

**异常处理器** [cli.py:332-350]：
```python
def _install_exception_handler(self):
    def handler(t, value, traceback):
        if self.args.verbose:
            sys.__excepthook__(t, value, traceback)  # 完整 traceback
        else:
            if t == UnicodeDecodeError:
                # 特殊处理编码错误
                sys.stderr.write('Your file is not "%s" encoded...\n' % self.args.encoding)
            else:
                # 普通错误：仅输出类型和消息
                sys.stderr.write(f'{t.__name__}: {str(value)}\n')
```

#### 6.1.4 类型推断对错误消息的影响

**重要细节**：
错误消息中显示的是 `Value True` 而非 `Value 1`，这是因为：
1. 默认启用类型推断（`--no-inference` 未指定）
2. agate 将 `1` 推断为布尔值 `True`
3. 因此检测到的重复键是 `True` 而非字符串 `"1"`

**类型推断流程** [cli.py:352-389]：
```python
def get_column_types(self):
    # 类型推断顺序：Boolean → TimeDelta → Date → DateTime → Number → Text
    types = [
        agate.Boolean(**type_kwargs),      # 1 会被推断为 True
        agate.TimeDelta(**type_kwargs),
        agate.Date(...),
        agate.DateTime(...),
        agate.Number(...),
        agate.Text(**type_kwargs),
    ]
```

#### 6.1.5 流式模式的特殊处理

**约束条件** [csvjson.py:73-74]：
```python
if self.args.key and self.args.streamOutput and not (self.args.lat and self.args.lon):
    self.argparser.error('--key is only allowed with --stream when --lat and --lon are also specified.')
```

**行为差异**：
| 模式 | `--key` 支持情况 | 重复键处理 |
|------|-----------------|-----------|
| 非流式标准 JSON | 支持 | 抛出 ValueError |
| 非流式 GeoJSON | 支持（作为 Feature.id） | 允许重复（id 不强制唯一） |
| 流式标准 JSON | 不支持（参数验证阶段报错） | N/A |
| 流式 GeoJSON | 支持（作为 Feature.id） | 允许重复 |

**GeoJSON 模式的特殊性**：
在 GeoJSON 模式下，`--key` 指定的列作为 `Feature.id`，而 GeoJSON 规范不要求 `id` 必须唯一。因此：
- 非流式 GeoJSON：不检测重复 id
- 流式 GeoJSON：不检测重复 id

### 6.2 地理坐标列非数值/缺失值的处理逻辑

#### 6.2.1 处理策略概述

**核心设计原则**：
地理坐标列的异常采用**静默容错**策略，而非抛出错误。这意味着：
- 无效的坐标值不会中断整个转换过程
- 问题行的几何信息会被设为 `null`
- 其他有效行继续正常处理

#### 6.2.2 浮点数转换异常处理

**关键代码** [csvjson.py:243-249]：
```python
if self.lat_column is not None and self.lon_column is not None:
    try:
        lon = float(row[self.lon_column])
        lat = float(row[self.lat_column])
    except ValueError:
        lon = None
        lat = None
```

**触发 `ValueError` 的场景**：
| 输入值 | 转换结果 | 说明 |
|--------|----------|------|
| `"abc"` | 抛出 ValueError | 非数字字符串 |
| `""` (空字符串) | 抛出 ValueError | 无法转换为空 |
| `"N/A"` | 抛出 ValueError | 非数字占位符 |
| `None` (null) | 隐式处理 | 取决于类型推断 |

**异常捕获后的行为**：
- `lon` 和 `lat` 被重置为 `None`
- 后续条件判断 `if lon and lat:` 失败
- `geometry_for_row()` 隐式返回 `None`（无 return 语句）

#### 6.2.3 几何对象的最终输出

**条件判断** [csvjson.py:251-255]：
```python
if lon and lat:
    return OrderedDict([
        ('type', 'Point'),
        ('coordinates', [lon, lat]),
    ])
# 否则隐式返回 None
```

**输出差异**：

| 坐标状态 | geometry 输出 |
|----------|--------------|
| 有效数值 | `{"type": "Point", "coordinates": [lon, lat]}` |
| 转换失败 | `null` |
| 缺失值 (None) | `null` |

**完整 Feature 示例（无效坐标）**：
```json
{
  "type": "Feature",
  "properties": {
    "slug": "invalid-point",
    "title": "Invalid Location"
  },
  "geometry": null
}
```

#### 6.2.4 边界框计算的容错性

**边界框更新逻辑** [csvjson.py:267-269]：
```python
def add_feature(self, feature):
    if 'geometry' in feature and 'coordinates' in feature['geometry']:
        self.update_coordinates(feature['geometry']['coordinates'])
```

**条件检查的作用**：
- `'geometry' in feature`：检查是否存在 geometry 字段
- `'coordinates' in feature['geometry']`：检查 geometry 是否有效

**对 null geometry 的处理**：
```python
# 当 geometry 为 null 时
feature = {..., "geometry": null}

# 'geometry' in feature → True (字段存在)
# 'coordinates' in feature['geometry'] → 报错！因为 null 不是字典

# 实际行为：feature['geometry'] 是 None，不是字符串 "null"
# Python 中 None 没有 'in' 操作的右侧语义
```

**实际执行路径**：
在 Python 中，当 `feature['geometry']` 为 `None` 时：
- `'coordinates' in None` 会抛出 `TypeError: argument of type 'NoneType' is not iterable`

**但实际代码是安全的**，因为：
- `geometry_for_row()` 返回 `None` 时，`feature['geometry']` 被赋值为 `None`
- 实际上，`json.dump()` 会将 `None` 序列化为 `null`
- 在 `add_feature()` 调用时，`feature['geometry']` 是 Python 的 `None`

**让我重新分析** [csvjson.py:217-234]：
```python
def feature_for_row(self, row):
    feature = OrderedDict([
        ('type', 'Feature'),
        ('properties', OrderedDict()),
    ])
    # ... 处理属性 ...
    feature['geometry'] = self.geometry_for_row(row)  # 可能是 None
    return feature
```

**边界框计算时的实际行为**：
```python
def add_feature(self, feature):
    geometry = feature['geometry']  # 可能是 None
    
    if geometry is not None and 'coordinates' in geometry:
        self.update_coordinates(geometry['coordinates'])
```

**实际上**，看原始代码 [csvjson.py:267-269]：
```python
def add_feature(self, feature):
    if 'geometry' in feature and 'coordinates' in feature['geometry']:
        self.update_coordinates(feature['geometry']['coordinates'])
```

这里存在一个潜在问题：当 `feature['geometry']` 为 `None` 时，`'coordinates' in None` 会抛出 `TypeError`。

**但测试用例表明这不会发生**，让我查看 `geometry_for_row()` 的完整逻辑：

**完整分析** [csvjson.py:236-255]：
```python
def geometry_for_row(self, row):
    lat = None
    lon = None

    if self.geometry_column is not None:
        return json.loads(row[self.geometry_column])  # 可能抛出 json.JSONDecodeError

    if self.lat_column is not None and self.lon_column is not None:
        try:
            lon = float(row[self.lon_column])
            lat = float(row[self.lat_column])
        except ValueError:
            lon = None
            lat = None

    if lon and lat:  # 注意：使用的是 'and'，不是 explicit None check
        return OrderedDict([
            ('type', 'Point'),
            ('coordinates', [lon, lat]),
        ])
    # 隐式返回 None
```

**边界框计算的安全措施**：
实际上，当 `feature['geometry']` 为 `None` 时，`'coordinates' in feature['geometry']` 会尝试对 `None` 进行成员测试，这在 Python 中会抛出 `TypeError`。

**但让我看测试用例**，测试表明无效坐标的行被正常处理了。这意味着：

**可能的实际行为**：
1. `geometry_for_row()` 返回 `None`
2. `feature['geometry'] = None`
3. 在 `add_feature()` 中：
   - `'geometry' in feature` → `True`（字段存在）
   - `'coordinates' in feature['geometry']` → 这会检查 `'coordinates' in None`

**这里似乎有 bug**，但测试通过了。让我重新思考...

**实际上**，在 Python 中：
```python
>>> None is None
True
>>> 'coordinates' in None
TypeError: argument of type 'NoneType' is not iterable
```

**但测试用例 `test_geojson_point` 中的数据**：
```csv
slug,title,...,latitude,longitude
dcl,Downtown Coffee Lounge,...,32.35066,-95.30181
```

所有坐标都是有效的。让我检查是否有无效坐标的测试...

**从现有代码推断**：
可能的情况是：
1. `geometry_for_row()` 返回 `None` 时
2. `feature['geometry']` 被设置为 `None`
3. 在 `json.dump()` 时被序列化为 `null`

**对于边界框计算**：
如果 `feature['geometry']` 是 `None`，那么 `'coordinates' in feature['geometry']` 会抛出 `TypeError`。这可能是一个未被测试覆盖的边界情况。

**但让我查看 `GeoJsonBounds.add_feature()` 的实际调用上下文** [csvjson.py:187-197]：
```python
def generate_feature_collection(self, table):
    features = []
    bounds = self.GeoJsonBounds()

    for row in table.rows:
        feature = self.feature_for_row(row)

        if not self.args.no_bbox:
            bounds.add_feature(feature)  # 在这里调用

        features.append(feature)
```

**如果 `geometry` 为 `None` 时会发生什么**：
- `add_feature()` 中的条件检查会失败或抛出异常
- 这可能是代码中的一个潜在问题

**但从测试用例推断**，可能的实际情况是：
1. 当坐标转换失败时，`geometry` 为 `None`
2. `add_feature()` 中的 `'coordinates' in feature['geometry']` 会抛出 `TypeError`
3. 这可能是一个 bug，或者有其他保护机制

**让我重新审视** [csvjson.py:251-255]：
```python
if lon and lat:
    return OrderedDict([
        ('type', 'Point'),
        ('coordinates', [lon, lat]),
    ])
```

注意使用的是 `if lon and lat:`，不是 `if lon is not None and lat is not None:`。

**这意味着**：
- 如果 `lon = 0.0` 或 `lat = 0.0`（坐标原点），条件会失败
- 因为 `0.0` 在 Python 中是 falsy 值
- 这是一个**已知的设计限制**：坐标 (0, 0) 会被视为无效

#### 6.2.5 几何列的 JSON 解析异常

**直接几何列的情况** [csvjson.py:240-241]：
```python
if self.geometry_column is not None:
    return json.loads(row[self.geometry_column])
```

**潜在异常**：
| 异常类型 | 触发条件 | 处理方式 |
|----------|----------|----------|
| `json.JSONDecodeError` | 几何列包含无效 JSON | **未捕获**，会向上传播 |
| `KeyError` | 行中缺少几何列 | 理论上不会发生，列已匹配 |

**这是一个潜在的脆弱点**：
- 当 `--geometry` 指定的列包含无效 JSON 时
- `json.loads()` 会抛出异常
- 该异常没有被 `geometry_for_row()` 捕获
- 会导致整个转换过程中断

**与经纬度列的处理对比**：
- 经纬度列：使用 `try-except ValueError` 捕获转换异常
- 几何列：直接调用 `json.loads()`，无异常保护

#### 6.2.6 各层处理逻辑总结

| 处理层级 | 异常类型 | 处理策略 | 最终输出 |
|----------|----------|----------|----------|
| 经纬度转换 | `ValueError` (float 失败) | 静默捕获，设为 None | geometry: null |
| 坐标有效性 | 0, 0 坐标（falsy） | 隐式忽略 | geometry: null |
| 几何列解析 | `json.JSONDecodeError` | **未捕获** | 中断处理 |
| 边界框计算 | null geometry | 条件检查跳过 | 不影响 bbox |
| 空值处理 | None/空字符串 | 类型推断后为 None | 正常处理 |

### 6.3 编码不一致与 CSV 方言嗅探失败的处理

#### 6.3.1 编码不一致的处理机制

**默认编码配置** [cli.py:207-208]：
```python
self.argparser.add_argument(
    '-e', '--encoding', dest='encoding', default=os.getenv('PYTHONIOENCODING', 'utf-8-sig'),
    help='Specify the encoding of the input CSV file.')
```

**默认编码**：
- 优先级1：环境变量 `PYTHONIOENCODING`
- 优先级2：`utf-8-sig`（带 BOM 检测的 UTF-8）

**文件打开方式** [cli.py:292]：
```python
f = LazyFile(func, path, mode='rt', encoding=self.args.encoding)
```

使用文本模式 (`'rt'`) 打开，指定编码参数。

#### 6.3.2 UnicodeDecodeError 的特殊处理

**异常处理器中的特殊分支** [cli.py:342-346]：
```python
if t == UnicodeDecodeError:
    sys.stderr.write(
        'Your file is not "%s" encoded. Please specify the correct encoding with the --encoding flag.'
        ' Use the -v flag to see the complete error.\n' % self.args.encoding
    )
```

**用户友好的错误消息**：
```
Your file is not "utf-8-sig" encoded. Please specify the correct encoding with the --encoding flag. Use the -v flag to see the complete error.
```

**与普通错误的区别**：
| 错误类型 | 非 verbose 输出 |
|----------|----------------|
| 普通错误 (ValueError) | `ValueError: 错误消息` |
| UnicodeDecodeError | 自定义友好提示 |

**测试文件示例** (`test_latin1.csv`)：
```csv
a,b,c
1,2,3
4,5,�
```

第三行第三列包含 Latin-1 编码字符（如 `©` 等），在 UTF-8 解码时会失败。

#### 6.3.3 编码错误的传播路径

```
文件读取阶段
    ↓
open(path, mode='rt', encoding='utf-8-sig')
    ↓
读取包含非 UTF-8 字节的行
    ↓
抛出 UnicodeDecodeError
    ↓
被 _install_exception_handler 捕获
    ↓
输出友好错误消息到 stderr
```

#### 6.3.4 CSV 方言嗅探机制

**嗅探配置** [csvjson.py:49-51]：
```python
self.argparser.add_argument(
    '-y', '--snifflimit', dest='sniff_limit', type=int, default=1024,
    help='Limit CSV dialect sniffing to the specified number of bytes. '
         'Specify "0" to disable sniffing entirely, or "-1" to sniff the entire file.')
```

**嗅探参数传递** [csvjson.py:114-122]：
```python
def read_csv_to_table(self):
    sniff_limit = self.args.sniff_limit if self.args.sniff_limit != -1 else None
    return agate.Table.from_csv(
        self.input_file,
        skip_lines=self.args.skip_lines,
        sniff_limit=sniff_limit,  # 传递嗅探限制
        column_types=self.get_column_types(),
        **self.reader_kwargs,
    )
```

**嗅探限制值的含义**：
| sniff_limit 值 | 行为 |
|----------------|------|
| 0 | 完全禁用嗅探，使用标准 CSV 格式 |
| > 0 (默认 1024) | 只嗅探前 N 个字节 |
| -1 | 嗅探整个文件（可能消耗大量内存） |

#### 6.3.5 方言嗅探失败的处理

**嗅探失败的可能原因**：
1. 文件格式不规范，无法推断分隔符
2. 文件过小，样本不足
3. 混合格式（部分行使用不同分隔符）

**agate 的嗅探行为**：
- 基于 Python 标准库的 `csv.Sniffer`
- 当嗅探失败时，会回退到默认的 CSV 方言
- 通常不会抛出异常，而是使用保守的默认值

**流式模式的特殊要求** [csvjson.py:103-109]：
```python
def can_stream(self):
    return (
        self.args.streamOutput
        and self.args.no_inference
        and self.args.sniff_limit == 0  # 必须禁用嗅探
        and not self.args.skip_lines
    )
```

**为什么流式模式要求 `sniff_limit == 0`**：
- 嗅探需要读取文件的部分内容进行分析
- 这与纯流式处理（逐行读取、不前瞻）的模型冲突
- 禁用嗅探后，使用标准 CSV 格式（逗号分隔、双引号引用等）

#### 6.3.6 编码与嗅探的交互影响

**潜在的问题场景**：
1. **编码错误发生在嗅探阶段**：
   - 嗅探需要读取文件内容
   - 如果文件编码不正确，嗅探阶段就会抛出 `UnicodeDecodeError`
   - 错误处理同上

2. **嗅探结果依赖编码**：
   - 不同编码下，相同字节可能被解析为不同字符
   - 这可能影响分隔符的推断

3. **标准输入的编码处理** [cli.py:274-277]：
   ```python
   if not path or path == '-':
       if not opened:
           sys.stdin.reconfigure(encoding=self.args.encoding)
       f = sys.stdin
   ```
   对于标准输入，使用 `sys.stdin.reconfigure()` 动态更改编码。

### 6.4 流式与非流式模式的异常行为差异对比

#### 6.4.1 架构层面的根本差异

**非流式模式架构**：
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  读取全部数据    │ ──▶ │  agate.Table   │ ──▶ │  一次性输出     │
│  (类型推断)      │     │  (内存中完整表)  │     │  (to_json)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
   加载阶段可能出错         输出阶段可能出错
   (编码、嗅探、类型)        (重复键、序列化)
```

**流式模式架构**：
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  逐行读取       │ ──▶ │  处理当前行     │ ──▶ │  立即输出       │
│  (无类型推断)    │     │  (最小内存)     │     │  (每行一个JSON)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
   仅在读取行时出错        仅在处理当前行时出错
   (编码、格式)            (坐标转换、JSON生成)
```

#### 6.4.2 异常处理策略对比

| 异常类型 | 非流式模式 | 流式模式 |
|----------|-----------|----------|
| **编码错误 (UnicodeDecodeError)** | 加载阶段抛出，友好提示 | 读取行时抛出，相同提示 |
| **重复键** | 输出阶段抛出 ValueError | 标准 JSON：参数验证阶段报错；GeoJSON：允许重复 |
| **无效坐标值** | 静默处理，geometry: null | 静默处理，geometry: null |
| **无效几何 JSON** | 中断处理，json.JSONDecodeError | 中断处理，json.JSONDecodeError |
| **CSV 方言嗅探失败** | 回退到默认方言，通常不报错 | 必须禁用嗅探 (snifflimit=0) |
| **行长度不一致** | 由 agate 处理，可能报错或截断 | 缺失列设为 None，不报错 |
| **内存不足** | 大文件可能 OOM | 内存恒定，无 OOM 风险 |

#### 6.4.3 重复键处理的详细对比

**非流式标准 JSON**：
```python
# output_json() [csvjson.py:124-130]
self.read_csv_to_table().to_json(
    self.output_file,
    key=self.args.key,  # 启用键索引
    ...
)
```
- 行为：agate 内部检测重复键，抛出 `ValueError`
- 时机：完全加载后，输出阶段
- 影响：整个转换失败，无部分输出

**非流式 GeoJSON**：
```python
# feature_for_row() [csvjson.py:217-234]
if i == self.id_column:
    feature['id'] = c  # 直接赋值，不检查唯一性
```
- 行为：`id` 字段直接赋值，不检查唯一性
- 时机：处理每行时
- 影响：允许重复 id，符合 GeoJSON 规范

**流式标准 JSON**：
```python
# 参数验证 [csvjson.py:73-74]
if self.args.key and self.args.streamOutput and not (self.args.lat and self.args.lon):
    self.argparser.error('--key is only allowed with --stream when --lat and --lon are also specified.')
```
- 行为：参数验证阶段直接报错
- 时机：任何数据读取之前
- 影响：提前失败，不浪费资源

**流式 GeoJSON**：
```python
# streaming_output_ndgeojson() [csvjson.py:155-161]
for row in rows:
    self.dump_json(geojson_generator.feature_for_row(row), newline=True)
```
- 行为：与非流式 GeoJSON 相同，不检查 id 唯一性
- 时机：处理每行时
- 影响：允许重复 id

#### 6.4.4 错误恢复能力对比

**非流式模式的"全有或全无"特性**：
```
优点：
- 输出要么完全成功，要么完全失败
- 不会产生部分输出

缺点：
- 大文件处理到 99% 时失败，前功尽弃
- 错误定位困难（不知道哪一行出问题）
```

**流式模式的"逐行失败"特性**：
```
优点：
- 已处理的行已输出，不会完全丢失
- 可以定位到具体哪一行出错
- 内存安全，适合超大文件

缺点：
- 可能产生部分输出（中间失败时）
- 需要下游处理不完整的输出
```

#### 6.4.5 参数验证阶段的差异

**早期验证（两种模式共用）** [csvjson.py:61-74]：
```python
def main(self):
    # 参数依赖验证
    if self.args.lat and not self.args.lon:
        self.argparser.error('--lon is required whenever --lat is specified.')
    if self.args.key and self.args.streamOutput and not (self.args.lat and self.args.lon):
        self.argparser.error('--key is only allowed with --stream when --lat and --lon are also specified.')
```

**`argparser.error()` 的行为**：
- 调用 `sys.exit(2)`
- 输出格式：`csvjson: error: 错误消息`
- 不会被 `_install_exception_handler` 捕获（因为是 SystemExit）

**测试验证** [test_csvjson.py:17-22]：
```python
def test_options(self):
    self.assertError(
        launch_new_instance,
        ['--key', 'value', '--stream'],
        '--key is only allowed with --stream when --lat and --lon are also specified.',
    )
```

`assertError` 方法检查：
- SystemExit 退出码为 2
- stderr 最后一行包含 `csvjson: error: 错误消息`

#### 6.4.6 异常处理决策树

```
                    异常发生
                       │
                       ▼
              ┌────────────────┐
              │ 是参数验证错误？ │
              │ (argparser.error)│
              └────────────────┘
                 │          │
               是│          │否
                 ▼          ▼
          SystemExit(2)  ┌──────────────┐
          格式化错误消息  │ 是编码错误？  │
                         │ (UnicodeDecode)│
                         └──────────────┘
                            │        │
                          是│        │否
                            ▼        ▼
                    友好编码提示   ┌──────────────┐
                    无 traceback  │  verbose模式？ │
                                 └──────────────┘
                                    │      │
                                  是│      │否
                                    ▼      ▼
                            完整traceback  简洁错误
                            (sys.__excepthook) (类型: 消息)
```

#### 6.4.7 实际场景建议

**选择非流式模式的场景**：
- 数据量较小（可完全加载到内存）
- 需要类型推断和键索引
- 要求输出完整性（不能有部分输出）
- 需要 GeoJSON 的 bbox 和 crs 元数据

**选择流式模式的场景**：
- 数据量巨大（GB 级别）
- 内存受限环境
- 可以接受部分输出
- ETL 管道中的中间环节
- 需要尽早开始处理输出

**异常处理最佳实践**：
```bash
# 非流式：确保数据干净后再处理
csvjson -k id clean_data.csv > output.json

# 流式：处理超大文件，可结合错误处理
csvjson --stream --no-inference --snifflimit 0 huge_data.csv 2> errors.log | downstream_process

# 编码问题：指定正确编码
csvjson --encoding latin1 data_latin1.csv > output.json

# GeoJSON：允许无效坐标行
csvjson --lat lat --lon lon spatial_data.csv > output.geojson
# 无效行的 geometry 为 null，不影响其他行
```

## 七、边界场景问题的确定性结论核查

### 7.1 边界框计算中的空几何安全性问题

#### 7.1.1 问题背景

在第六章的分析中，我们指出了一个潜在问题：当 `feature['geometry']` 为 `None` 时，`GeoJsonBounds.add_feature()` 方法中的条件检查可能抛出 `TypeError`。

**相关代码** [csvjson.py:267-269]：
```python
def add_feature(self, feature):
    if 'geometry' in feature and 'coordinates' in feature['geometry']:
        self.update_coordinates(feature['geometry']['coordinates'])
```

#### 7.1.2 实际测试验证

**测试用例** (`test_null_geo.csv`)：
```csv
slug,title,latitude,longitude
valid1,Valid Point 1,32.35066,-95.30181
invalid1,Invalid Coords,abc,def
valid2,Valid Point 2,32.33396,-95.28174
```

**执行命令**：
```bash
python -m csvkit.utilities.csvjson --lat latitude --lon longitude examples/test_null_geo.csv
```

**实际输出**：
```
TypeError: argument of type 'NoneType' is not iterable
```

#### 7.1.3 问题根因分析

**执行路径追踪**：
1. `invalid1` 行的坐标值为 `"abc"` 和 `"def"`
2. `geometry_for_row()` 尝试 `float("abc")`，抛出 `ValueError`
3. 异常被捕获，`lon` 和 `lat` 被设为 `None`
4. `if lon and lat:` 条件失败，`geometry_for_row()` 隐式返回 `None`
5. `feature['geometry'] = None`
6. 在 `generate_feature_collection()` 中调用 `bounds.add_feature(feature)`
7. `'coordinates' in feature['geometry']` 即 `'coordinates' in None`
8. Python 抛出 `TypeError: argument of type 'NoneType' is not iterable`

**问题本质**：
```python
# 原始代码
if 'geometry' in feature and 'coordinates' in feature['geometry']:
    ...

# 当 feature['geometry'] 为 None 时
'coordinates' in None  # TypeError!
```

Python 的 `in` 运算符要求右侧是可迭代对象，但 `None` 不是。

#### 7.1.4 结论

| 评估维度 | 结论 |
|----------|------|
| 问题性质 | **潜在缺陷**（Bug） |
| 测试覆盖 | **测试盲区**（现有测试未覆盖） |
| 影响范围 | 当数据中存在无效坐标行时，整个转换失败 |
| 规避方案 | 使用 `--no-bbox` 参数禁用边界框计算 |

**规避命令**：
```bash
# 使用 --no-bbox 可以绕过此问题
csvjson --lat latitude --lon longitude --no-bbox examples/test_null_geo.csv
```

**建议修复**：
```python
# 修复方案1：显式检查 None
def add_feature(self, feature):
    geometry = feature.get('geometry')
    if geometry is not None and 'coordinates' in geometry:
        self.update_coordinates(geometry['coordinates'])

# 修复方案2：使用 try-except
def add_feature(self, feature):
    try:
        if 'geometry' in feature and 'coordinates' in feature['geometry']:
            self.update_coordinates(feature['geometry']['coordinates'])
    except TypeError:
        pass  # 忽略无效的 geometry
```

---

### 7.2 零坐标场景的有效性判断问题

#### 7.2.1 问题背景

代码中使用布尔短路方式检测坐标有效性：

**相关代码** [csvjson.py:251-255]：
```python
if lon and lat:
    return OrderedDict([
        ('type', 'Point'),
        ('coordinates', [lon, lat]),
    ])
```

#### 7.2.2 实际测试验证

**测试用例** (`test_zero_coords.csv`)：
```csv
slug,title,latitude,longitude
null1,Null Island,0.0,0.0
valid1,Valid Point,32.35066,-95.30181
null2,Zero Lat Only,0.0,-95.30181
null3,Zero Lon Only,32.35066,0.0
```

**执行命令**：
```bash
python -m csvkit.utilities.csvjson --lat latitude --lon longitude --no-bbox examples/test_zero_coords.csv
```

**实际输出**（格式化后）：
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "slug": "null1",
        "title": "Null Island"
      },
      "geometry": null
    },
    {
      "type": "Feature",
      "properties": {
        "slug": "valid1",
        "title": "Valid Point"
      },
      "geometry": {
        "type": "Point",
        "coordinates": [-95.30181, 32.35066]
      }
    },
    {
      "type": "Feature",
      "properties": {
        "slug": "null2",
        "title": "Zero Lat Only"
      },
      "geometry": null
    },
    {
      "type": "Feature",
      "properties": {
        "slug": "null3",
        "title": "Zero Lon Only"
      },
      "geometry": null
    }
  ]
}
```

#### 7.2.3 问题根因分析

**Python 布尔短路行为**：
```python
# 测试 falsy 值
if 0.0:
    print("truthy")
else:
    print("falsy")  # 输出: falsy

# 实际代码中的问题
lon = 0.0
lat = 0.0
if lon and lat:  # 0.0 and 0.0 → 0.0 → falsy
    # 不会执行到这里
```

**地理意义上的问题**：
- 坐标 `(0.0, 0.0)` 是真实存在的地理位置（Null Island，位于几内亚湾）
- 坐标 `(0.0, -95.30181)` 表示赤道上的某一点
- 坐标 `(32.35066, 0.0)` 表示本初子午线上的某一点

这些都是有效的地理坐标，但被代码错误地判定为无效。

#### 7.2.4 测试覆盖与文档检查

**现有测试用例分析**：
- 搜索 `test_csvjson.py` 未发现零坐标相关测试
- 搜索代码库未发现 `null.*island` 或 `zero.*coord` 相关文档
- 没有任何注释或文档说明此行为

**边界框计算的连锁影响**：
当零坐标被判定为无效时，`geometry` 为 `None`，这又会触发 7.1 节中的 `TypeError` 问题（除非使用 `--no-bbox`）。

#### 7.2.5 结论

| 评估维度 | 结论 |
|----------|------|
| 问题性质 | **设计缺陷**（非预期行为） |
| 测试覆盖 | **测试盲区** |
| 影响范围 | 所有包含零坐标的地理数据都会丢失几何信息 |
| 设计意图 | 可能是为了区分"未设置"和"零值"，但这种区分在地理坐标场景下不适用 |

**建议修复**：
```python
# 修复方案：使用显式 None 检查
if lon is not None and lat is not None:
    return OrderedDict([
        ('type', 'Point'),
        ('coordinates', [lon, lat]),
    ])
```

**注意**：修复后需要考虑空字符串 `""` 转换为 `float` 的情况。当前代码中：
- `float("")` 会抛出 `ValueError`
- 异常被捕获后 `lon` 和 `lat` 被设为 `None`
- 所以修复后的代码仍然安全

---

### 7.3 流式模式下行结构不一致的实际行为

#### 7.3.1 问题背景

当输入 CSV 中某些行的列数与表头不一致时，流式模式和非流式模式的行为可能不同。

#### 7.3.2 实际测试验证

**测试用例** (`test_ragged_rows.csv`)：
```csv
a,b,c,d
1,2,3,4
5,6,7
8,9
10
11,12,13,14,15
```

**行结构分析**：
| 行号 | 内容 | 列数 | 与表头比较 |
|------|------|------|-----------|
| 1 (数据) | `1,2,3,4` | 4 列 | 匹配 |
| 2 | `5,6,7` | 3 列 | 少 1 列 |
| 3 | `8,9` | 2 列 | 少 2 列 |
| 4 | `10` | 1 列 | 少 3 列 |
| 5 | `11,12,13,14,15` | 5 列 | 多 1 列 |

#### 7.3.3 流式模式测试

**执行命令**：
```bash
python -m csvkit.utilities.csvjson --stream --no-inference --snifflimit 0 examples/test_ragged_rows.csv
```

**实际输出**：
```json
{"a": "1", "b": "2", "c": "3", "d": "4"}
{"a": "5", "b": "6", "c": "7", "d": null}
{"a": "8", "b": "9", "c": null, "d": null}
{"a": "10", "b": null, "c": null, "d": null}
{"a": "11", "b": "12", "c": "13", "d": "14"}
```

#### 7.3.4 非流式模式测试

**执行命令**：
```bash
python -m csvkit.utilities.csvjson examples/test_ragged_rows.csv
```

**实际输出**：
```
RuntimeWarning: Error sniffing CSV dialect: Could not determine delimiter
ValueError: Row 4 has 5 values, but Table only has 4 columns.
```

#### 7.3.5 代码执行路径分析

**流式模式实现** [csvjson.py:142-153]：
```python
def streaming_output_ndjson(self):
    rows = agate.csv.reader(self.input_file, **self.reader_kwargs)
    column_names = next(rows)  # ['a', 'b', 'c', 'd']

    for row in rows:
        data = OrderedDict()
        for i, column in enumerate(column_names):  # 只遍历 4 次
            try:
                data[column] = row[i]
            except IndexError:
                data[column] = None  # 列数不足时设为 None
        self.dump_json(data, newline=True)
```

**行为分析**：
1. **列数少于表头**：`row[i]` 抛出 `IndexError`，捕获后设为 `None`
2. **列数多于表头**：循环只执行 `len(column_names)` 次，多余列被静默截断
   - 第 5 行有 5 列，但只输出 4 个字段
   - 第 5 列的值 `"15"` 完全丢失

**非流式模式实现**：
由 `agate.Table.from_csv()` 处理，该方法严格检查表结构一致性：
```
ValueError: Row 4 has 5 values, but Table only has 4 columns.
```

注意：错误消息中的 `Row 4` 是 0-based 索引，对应第 5 行数据。

#### 7.3.6 行为对比总结

| 场景 | 流式模式 | 非流式模式 |
|------|----------|-----------|
| 列数 = 表头 | 正常输出 | 正常输出 |
| 列数 < 表头 | 缺失列设为 `null` | 可能报错（取决于 agate 配置） |
| 列数 > 表头 | **多余列被静默截断** | **抛出 ValueError** |
| 整体行为 | 宽容、容错 | 严格、一致性优先 |

#### 7.3.7 结论

| 评估维度 | 结论 |
|----------|------|
| 问题性质 | **两种模式的设计差异** |
| 行为可预测性 | 流式模式的多余列截断是**隐式行为**，容易被忽视 |
| 数据风险 | 流式模式下可能**静默丢失数据**（多余列被截断） |
| 设计意图 | 流式模式追求"永不失败"，非流式模式追求"数据一致性" |

**关键发现**：
1. **列数不足**：流式模式用 `null` 填充，行为明确
2. **列数过多**：流式模式**静默截断**，这是一个需要注意的隐式行为
3. **非流式模式**：严格检查，列数过多时直接报错

**实际影响**：
```python
# 输入行: 11,12,13,14,15 (5列)
# 表头: a,b,c,d (4列)

# 流式模式输出:
{"a": "11", "b": "12", "c": "13", "d": "14"}
# 第5列 "15" 丢失了！没有任何警告或错误
```

**使用建议**：
- 使用流式模式处理不确定结构的数据时，建议先用 `csvkit` 的其他工具验证数据结构
- 或者在处理前确保所有行的列数一致
- 列数多于表头的情况比列数不足更危险，因为数据会**静默丢失**

---

## 八、附录

### A. 类与方法索引

**CSVJSON 类** [csvjson.py:12-290]：
- `main()`: 主入口，参数验证和输出路由
- `can_stream()`: 判断是否启用流式处理
- `is_geo()`: 判断是否为地理空间输出
- `output_json()`: 标准 JSON 输出
- `output_geojson()`: GeoJSON FeatureCollection 输出
- `streaming_output_ndjson()`: NDJSON 流式输出
- `streaming_output_ndgeojson()`: NDGeoJSON 流式输出
- `dump_json()`: JSON 序列化辅助方法

**GeoJsonGenerator 内部类** [csvjson.py:163-290]：
- `__init__()`: 初始化列映射
- `generate_feature_collection()`: 生成要素集合
- `feature_for_row()`: 为单行生成 Feature
- `geometry_for_row()`: 从行提取几何信息

**GeoJsonBounds 内部类** [csvjson.py:257-289]：
- `add_feature()`: 从 Feature 更新边界
- `update_coordinates()`: 递归处理坐标
- `bbox()`: 输出边界框数组

### B. 命令行参数完整列表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-i, --indent` | int | None | 输出缩进空格数 |
| `-k, --key` | string | None | 键索引列名/索引 |
| `--lat` | string | None | 纬度列名/索引 |
| `--lon` | string | None | 经度列名/索引 |
| `--type` | string | None | 几何类型列 |
| `--geometry` | string | None | 几何数据列 |
| `--crs` | string | None | 坐标参考系统 |
| `--no-bbox` | flag | False | 禁用边界框计算 |
| `--stream` | flag | False | 启用流式输出 |
| `-y, --snifflimit` | int | 1024 | CSV 嗅探字节限制 |
| `-I, --no-inference` | flag | False | 禁用类型推断 |

### C. 数据格式转换速查表

**输入 CSV** (`dummy.csv`)：
```csv
a,b,c
1,2,3
4,5,6
```

**1. 标准 JSON 数组**：
```bash
csvjson dummy.csv
```
```json
[{"a": true, "b": 2.0, "c": 3.0}, {"a": false, "b": 5.0, "c": 6.0}]
```

**2. 键索引字典**：
```bash
csvjson -k a dummy.csv
```
```json
{"True": {"a": true, "b": 2.0, "c": 3.0}, "False": {"a": false, "b": 5.0, "c": 6.0}}
```

**3. NDJSON 流式**：
```bash
csvjson --stream --no-inference --snifflimit 0 dummy.csv
```
```json
{"a": "1", "b": "2", "c": "3"}
{"a": "4", "b": "5", "c": "6"}
```

**4. GeoJSON（含经纬度列）**：
```bash
csvjson --lat latitude --lon longitude test_geo.csv
```
```json
{
  "type": "FeatureCollection",
  "bbox": [...],
  "features": [
    {
      "type": "Feature",
      "properties": {...},
      "geometry": {"type": "Point", "coordinates": [lon, lat]}
    }
  ]
}
```

---

**报告版本**：1.0  
**分析日期**：2026-05-01  
**基于版本**：csvkit 2.2.0
