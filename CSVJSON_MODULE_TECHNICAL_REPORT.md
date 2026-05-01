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

## 六、附录

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
