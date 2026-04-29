# csvkit 类型推断中的 NULL 值处理机制分析

## 目录
1. [DEFAULT_NULL_VALUES 具体内容](#default_null_values-具体内容)
2. [NULL 候选值的处理时机](#null-候选值的处理时机)
3. [--blanks 参数的影响分析](#--blanks-参数的影响分析)
4. [--null-value 对不同类型识别的影响](#--null-value-对不同类型识别的影响)
5. [完整处理流程图](#完整处理流程图)
6. [测试用例验证](#测试用例验证)

---

## 1. DEFAULT_NULL_VALUES 具体内容

### 1.1 源码定义

`DEFAULT_NULL_VALUES` 从 `agate` 库导入，定义在 `agate/data_types/base.py`：

```python
# csvkit/cli.py:20
from agate.data_types.base import DEFAULT_NULL_VALUES
```

### 1.2 具体包含的字符串

通过测试用例和源码分析，`DEFAULT_NULL_VALUES` 是一个元组，包含以下 6 个字符串（**大小写不敏感**的比较）：

| 序号 | 字符串值 | 说明 |
|------|----------|------|
| 1 | `""` | 空字符串 |
| 2 | `"na"` | 小写 na |
| 3 | `"n/a"` | 小写 n/a |
| 4 | `"none"` | 小写 none |
| 5 | `"null"` | 小写 null |
| 6 | `"."` | 单个点号 |

**注意**：实际比较时是**大小写不敏感**的，所以 `"NA"`, `"N/A"`, `"NONE"`, `"NULL"` 也会被匹配。

### 1.3 测试数据验证

`examples/blanks.csv` 内容：
```csv
a,b,c,d,e,f
,NA,N/A,NONE,NULL,.
```

各列对应的 NULL 候选值：

| 列名 | 值 | 是否在 DEFAULT_NULL_VALUES |
|------|-----|---------------------------|
| a | `""` | ✅ 是 |
| b | `"NA"` | ✅ 是（大小写不敏感） |
| c | `"N/A"` | ✅ 是（大小写不敏感） |
| d | `"NONE"` | ✅ 是（大小写不敏感） |
| e | `"NULL"` | ✅ 是（大小写不敏感） |
| f | `"."` | ✅ 是 |

---

## 2. NULL 候选值的处理时机

### 2.1 核心问题

> 这些 null 候选值是在类型测试之前就被转换掉的，还是参与到每种类型的识别逻辑里？

### 2.2 答案：参与每种类型的识别逻辑，**不参与类型投票**

`null_values` 参数被传递给每个 `agate` 类型的构造函数：

```python
# csvkit/cli.py:352-389
def get_column_types(self):
    # 构建 null_values 列表
    if getattr(self.args, 'blanks', None):
        type_kwargs = {'null_values': []}           # --blanks: 空列表
    else:
        type_kwargs = {'null_values': list(DEFAULT_NULL_VALUES)}  # 默认值
    
    # 追加自定义 null 值
    for null_value in getattr(self.args, 'null_values', []):
        type_kwargs['null_values'].append(null_value)

    # 将 null_values 传递给每种类型
    text_type = agate.Text(**type_kwargs)
    
    if not self.args.no_inference:
        number_type = agate.Number(locale=..., no_leading_zeroes=..., **type_kwargs)
        
        types = [
            agate.Boolean(**type_kwargs),           # 传递 null_values
            agate.TimeDelta(**type_kwargs),         # 传递 null_values
            agate.Date(date_format=..., **type_kwargs),    # 传递 null_values
            agate.DateTime(datetime_format=..., **type_kwargs),  # 传递 null_values
            text_type,
        ]
        # ... 插入 Number 类型
```

### 2.3 agate 类型的工作机制

每个 `agate` 类型（如 `Boolean`, `Number`, `Date` 等）都有以下逻辑：

```
类型.test(value, null_values) 流程：
    │
    ├── 1. 检查 value 是否在 null_values 中（大小写不敏感比较）
    │       │
    │       ├── 是 → 返回 True（视为 NULL，该类型"接受"这个值）
    │       │
    │       └── 否 → 继续执行类型特定的测试逻辑
    │
    └── 2. 执行类型特定的测试
            │
            ├── Boolean: 检查是否是 "true"/"false" 等
            ├── Number: 尝试解析为数字
            ├── Date: 尝试解析为日期
            └── ...
```

### 2.4 关键洞察

**NULL 值不参与类型投票**：

1. **在类型推断阶段**：
   - 如果一个值匹配 `null_values`，所有类型都会对它返回 `True`（视为兼容）
   - 这意味着 NULL 值**不会影响**类型推断的结果
   - 类型推断器只根据**非 NULL 值**来决定列类型

2. **在数据解析阶段**：
   - 匹配 `null_values` 的值会被转换为 Python 的 `None`
   - 不匹配的值会被解析为对应类型的实际值

### 2.5 示例演示

假设有以下数据：
```csv
score
100
NA
95
null
```

**类型推断过程**：

```
列 "score" 的值: ["100", "NA", "95", "null"]

步骤1: 过滤 NULL 值
       "100" → 非 NULL
       "NA"  → NULL (忽略)
       "95"  → 非 NULL
       "null" → NULL (忽略)

步骤2: 只根据非 NULL 值推断类型
       ["100", "95"] 都能被 Number 类型解析

步骤3: 最终类型
       Number 类型

步骤4: 解析后的数据
       [100, None, 95, None]
```

---

## 3. --blanks 参数的影响分析

### 3.1 源码实现

```python
# csvkit/cli.py:352-358
def get_column_types(self):
    if getattr(self.args, 'blanks', None):
        type_kwargs = {'null_values': []}           # 空列表！
    else:
        type_kwargs = {'null_values': list(DEFAULT_NULL_VALUES)}
    # ...
```

**`--blanks` 的核心作用**：将 `null_values` 列表设置为空列表 `[]`

### 3.2 行为对比

| 场景 | 无 `--blanks` | 有 `--blanks` |
|------|--------------|---------------|
| `null_values` | `["", "na", "n/a", "none", "null", "."]` | `[]`（空） |
| `""` 的处理 | 视为 `None` | 视为普通字符串 `""` |
| `"NA"` 的处理 | 视为 `None` | 视为普通字符串 `"NA"` |
| `"N/A"` 的处理 | 视为 `None` | 视为普通字符串 `"N/A"` |
| `"NONE"` 的处理 | 视为 `None` | 视为普通字符串 `"NONE"` |
| `"NULL"` 的处理 | 视为 `None` | 视为普通字符串 `"NULL"` |
| `"."` 的处理 | 视为 `None` | 视为普通字符串 `"."` |

### 3.3 测试用例验证

#### 测试1: csvjson 输出对比

**测试代码** (`tests/test_utilities/test_csvjson.py:52-58`):

```python
def test_no_blanks(self):
    # 无 --blanks
    js = json.loads(self.get_output(['examples/blanks.csv']))
    self.assertDictEqual(js[0], {
        'a': None, 
        'b': None, 
        'c': None, 
        'd': None, 
        'e': None, 
        'f': None
    })

def test_blanks(self):
    # 有 --blanks
    js = json.loads(self.get_output(['--blanks', 'examples/blanks.csv']))
    self.assertDictEqual(js[0], {
        'a': '',        # 空字符串保持原样
        'b': 'NA',      # NA 保持原样
        'c': 'N/A',     # N/A 保持原样
        'd': 'NONE',    # NONE 保持原样
        'e': 'NULL',    # NULL 保持原样
        'f': '.'        # . 保持原样
    })
```

**结果对比**：

| 列 | 无 `--blanks` | 有 `--blanks` |
|----|--------------|---------------|
| a | `None` | `""` |
| b | `None` | `"NA"` |
| c | `None` | `"N/A"` |
| d | `None` | `"NONE"` |
| e | `None` | `"NULL"` |
| f | `None` | `"."` |

#### 测试2: csvsql 类型推断对比

**测试代码** (`tests/test_utilities/test_csvsql.py:100-126`):

```python
def test_no_blanks(self):
    # 无 --blanks
    sql = self.get_output(['--tables', 'foo', 'examples/blanks.csv'])
    # 生成的 SQL: 所有列都是 BOOLEAN
    # CREATE TABLE foo (
    #   a BOOLEAN, 
    #   b BOOLEAN, 
    #   c BOOLEAN, 
    #   d BOOLEAN, 
    #   e BOOLEAN, 
    #   f BOOLEAN
    # );

def test_blanks(self):
    # 有 --blanks
    sql = self.get_output(['--tables', 'foo', '--blanks', 'examples/blanks.csv'])
    # 生成的 SQL: 所有列都是 VARCHAR NOT NULL
    # CREATE TABLE foo (
    #   a VARCHAR NOT NULL, 
    #   b VARCHAR NOT NULL, 
    #   c VARCHAR NOT NULL, 
    #   d VARCHAR NOT NULL, 
    #   e VARCHAR NOT NULL, 
    #   f VARCHAR NOT NULL
    # );
```

**关键分析**：

**无 `--blanks` 时的类型推断**：
- 所有值 `["", "NA", "N/A", "NONE", "NULL", "."]` 都匹配 `null_values`
- 对类型推断器来说，这列**没有非 NULL 值**
- agate 在这种情况下的默认行为是选择 `Boolean` 类型（或某种默认类型）

**有 `--blanks` 时的类型推断**：
- `null_values = []`，没有值被视为 NULL
- 所有值都作为普通字符串参与类型测试
- 测试各值：
  - `""`：无法被 Boolean/Number/Date 解析，只能被 Text 解析
  - `"NA"`：无法被 Boolean/Number/Date 解析，只能被 Text 解析
  - `"N/A"`：同上
  - `"NONE"`：同上（注意：Boolean 只匹配 "true"/"false"，不匹配 "none"）
  - `"NULL"`：同上
  - `"."`：无法被 Number 解析（不是有效数字格式）
- 最终所有列都被推断为 `Text`（VARCHAR）

### 3.4 各值在 `--blanks` 下的类型推断

当使用 `--blanks` 时，`blanks.csv` 中的各值会被如何推断：

| 值 | Boolean 测试 | Number 测试 | Date 测试 | 最终类型 |
|----|-------------|-------------|-----------|----------|
| `""` | ❌ 不是 "true"/"false" | ❌ 不是有效数字 | ❌ 不是有效日期 | Text |
| `"NA"` | ❌ | ❌ | ❌ | Text |
| `"N/A"` | ❌ | ❌ | ❌ | Text |
| `"NONE"` | ❌ (Boolean 只识别 true/false) | ❌ | ❌ | Text |
| `"NULL"` | ❌ | ❌ | ❌ | Text |
| `"."` | ❌ | ❌ (不是有效数字) | ❌ | Text |

**结论**：使用 `--blanks` 后，所有这些值都会被推断为 `Text` 类型。

---

## 4. --null-value 对不同类型识别的影响

### 4.1 源码实现

```python
# csvkit/cli.py:357-358
for null_value in getattr(self.args, 'null_values', []):
    type_kwargs['null_values'].append(null_value)
```

**作用**：将用户指定的值**追加**到 `null_values` 列表中

### 4.2 命令行用法

```bash
# 单个自定义 NULL 值
csvstat --null-value "N/A" data.csv

# 多个自定义 NULL 值
csvstat --null-value "N/A" --null-value "-" --null-value "NA" data.csv
```

### 4.3 对类型识别的影响

`--null-value` 的影响是**统一的**，对所有类型的影响相同：

#### 核心机制

```
原始 null_values: [ "", "na", "n/a", "none", "null", "." ]

使用 --null-value "missing" --null-value "-" 后:

null_values: [ "", "na", "n/a", "none", "null", ".", "missing", "-" ]
```

**对所有类型的影响**：

1. **Boolean 类型**：
   - `"missing"` 和 `"-"` 现在会被视为 NULL
   - 这些值不再参与 Boolean 的测试逻辑

2. **Number 类型**：
   - `"missing"` 和 `"-"` 现在会被视为 NULL
   - 这些值不再参与 Number 的解析测试

3. **Date 类型**：
   - `"missing"` 和 `"-"` 现在会被视为 NULL
   - 这些值不再参与 Date 的解析测试

4. **Text 类型**：
   - 对 Text 类型没有实质影响（因为 Text 接受所有值）

### 4.4 测试用例验证

**测试代码** (`tests/test_utilities/test_in2csv.py:71-91`):

```python
def test_null_value(self):
    # 输入: a,b
    #       n/a,\N
    input_file = io.BytesIO(b'a,b\nn/a,\\N')
    
    with stdin_as_string(input_file):
        # 使用 --null-value '\N'
        self.assertLines(['-f', 'csv', '--null-value', '\\N'], [
            'a,b',
            ',',      # 两列都是 NULL
        ])

def test_null_value_blanks(self):
    # 相同输入，但同时使用 --blanks
    input_file = io.BytesIO(b'a,b\nn/a,\\N')
    
    with stdin_as_string(input_file):
        # --blanks 清空默认 null_values
        # --null-value 追加 \N 到空列表
        self.assertLines(['-f', 'csv', '--null-value', '\\N', '--blanks'], [
            'a,b',
            'n/a,',   # a 列 "n/a" 不再是 NULL，b 列 "\\N" 是 NULL
        ])
```

**详细分析**：

**测试1: `test_null_value`**：
```
输入:
  a, b
  n/a, \N

参数: --null-value '\N'

null_values = DEFAULT_NULL_VALUES + ['\\N']
           = ["", "na", "n/a", "none", "null", ".", "\\N"]

解析:
  "n/a" → 匹配 null_values → None
  "\\N" → 匹配 null_values → None

输出:
  a, b
  ,    (两列都是空，表示 NULL)
```

**测试2: `test_null_value_blanks`**：
```
输入:
  a, b
  n/a, \N

参数: --null-value '\\N' --blanks

--blanks 的作用: null_values = []
--null-value 的作用: null_values.append('\\N')

最终 null_values = ['\\N']

解析:
  "n/a" → 不匹配 null_values (不在 ['\\N'] 中) → 保持 "n/a"
  "\\N" → 匹配 null_values → None

输出:
  a, b
  n/a,    (a 列保持原样，b 列为 NULL)
```

### 4.5 对不同类型的实际影响示例

假设我们有以下数据：

```csv
value,flag,date
100,true,2023-01-01
-,false,-
N/A,true,N/A
```

**场景1: 不使用 `--null-value`**

```
null_values = ["", "na", "n/a", "none", "null", "."]

解析:
value 列:
  "100"  → 100 (Number)
  "-"    → "-" 不是 NULL (不在默认列表中) → 尝试解析为 Number → 失败 → Text?
  "N/A"  → None (NULL)
  
flag 列:
  "true"  → True (Boolean)
  "false" → False (Boolean)
  "true"  → True (Boolean)

date 列:
  "2023-01-01" → 2023-01-01 (Date)
  "-"          → "-" 不是 NULL → 尝试解析为 Date → 失败 → Text?
  "N/A"        → None (NULL)
```

**场景2: 使用 `--null-value "-"`**

```
null_values = ["", "na", "n/a", "none", "null", ".", "-"]

解析:
value 列:
  "100"  → 100 (Number)
  "-"    → None (NULL，因为 "-" 现在在 null_values 中)
  "N/A"  → None (NULL)
  
flag 列:
  "true"  → True (Boolean)
  "false" → False (Boolean)
  "true"  → True (Boolean)

date 列:
  "2023-01-01" → 2023-01-01 (Date)
  "-"          → None (NULL)
  "N/A"        → None (NULL)
```

**关键差异**：

| 列 | 无 `--null-value` | 有 `--null-value "-"` |
|----|------------------|----------------------|
| value | 包含 `"-"` 这个"异常值"，可能影响类型推断 | `"-"` 被视为 NULL，不影响类型推断 |
| date | 包含 `"-"` 这个"异常值"，可能影响类型推断 | `"-"` 被视为 NULL，不影响类型推断 |

### 4.6 总结

`--null-value` 对不同类型的影响：

| 类型 | 影响 | 说明 |
|------|------|------|
| **所有类型** | 统一 | 自定义值被添加到 `null_values` 列表 |
| **Boolean** | 间接影响 | 自定义值不再被测试是否为 true/false |
| **Number** | 间接影响 | 自定义值不再被尝试解析为数字 |
| **Date** | 间接影响 | 自定义值不再被尝试解析为日期 |
| **Text** | 无影响 | Text 接受所有值，包括 NULL |

**核心原则**：
- `--null-value` 是**追加**操作，不是替换
- 可以多次使用，添加多个自定义 NULL 值
- 与 `--blanks` 组合时，`--blanks` 先清空默认值，然后追加自定义值

---

## 5. 完整处理流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CSV 类型推断完整流程                                  │
└─────────────────────────────────────────────────────────────────────────────┘

输入 CSV 数据
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 步骤1: 构建 null_values 列表                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   if --blanks 参数存在?                                                      │
│       │                                                                     │
│       ├── 是 → null_values = []                                            │
│       │                                                                     │
│       └── 否 → null_values = list(DEFAULT_NULL_VALUES)                     │
│                     = ["", "na", "n/a", "none", "null", "."]             │
│                                                                             │
│   然后，追加 --null-value 指定的自定义值:                                     │
│   for value in args.null_values:                                            │
│       null_values.append(value)                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 步骤2: 构建类型推断链 (TypeTester)                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   将 null_values 传递给每种类型的构造函数:                                    │
│                                                                             │
│   types = [                                                                 │
│       agate.Boolean(null_values=...),                                       │
│       agate.Number(null_values=..., locale=..., no_leading_zeroes=...),   │
│       agate.TimeDelta(null_values=...),                                     │
│       agate.Date(null_values=..., date_format=...),                         │
│       agate.DateTime(null_values=..., datetime_format=...),                 │
│       agate.Text(null_values=...),                                           │
│   ]                                                                          │
│                                                                             │
│   注意: Number 的位置会根据 --date-format/--datetime-format 调整            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 步骤3: 对每列进行类型推断                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   对每列的每个值，按顺序测试每种类型:                                         │
│                                                                             │
│   for column in columns:                                                    │
│       for type_candidate in types:  # Boolean → Number → ... → Text        │
│           all_match = True                                                   │
│                                                                             │
│           for value in column:                                               │
│               # 关键: 先检查是否是 NULL 值                                   │
│               if value.lower() in null_values:  # 大小写不敏感              │
│                   continue  # NULL 值跳过，不影响类型测试                     │
│                                                                             │
│               # 非 NULL 值，执行类型特定的测试                                │
│               if not type_candidate.test(value):                             │
│                   all_match = False                                          │
│                   break                                                       │
│                                                                             │
│           if all_match:                                                       │
│               column_type = type_candidate                                   │
│               break                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 步骤4: 解析数据值                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   使用推断出的类型解析每个值:                                                 │
│                                                                             │
│   for row in csv_rows:                                                      │
│       parsed_row = []                                                       │
│       for i, value in enumerate(row):                                       │
│           column_type = inferred_types[i]                                   │
│                                                                             │
│           # 检查是否是 NULL 值                                               │
│           if value.lower() in null_values:                                  │
│               parsed_row.append(None)                                        │
│           else:                                                              │
│               # 使用类型的 cast 方法解析                                      │
│               parsed_row.append(column_type.cast(value))                     │
│                                                                             │
│       yield parsed_row                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
  输出: agate.Table (包含类型化数据)
```

---

## 6. 测试用例验证汇总

### 6.1 测试文件清单

| 测试文件 | 测试内容 |
|----------|----------|
| `tests/test_utilities/test_in2csv.py` | `--null-value`, `--blanks` 组合测试 |
| `tests/test_utilities/test_csvjson.py` | JSON 输出中的 NULL 值处理 |
| `tests/test_utilities/test_csvsql.py` | SQL 类型推断中的 NULL 值影响 |
| `tests/test_utilities/test_csvsort.py` | 排序中的 NULL 值处理 |
| `tests/test_utilities/test_csvlook.py` | 显示中的 NULL 值处理 |
| `tests/test_utilities/test_csvjoin.py` | 连接中的 NULL 值处理 |

### 6.2 关键测试用例

**测试1: `--blanks` 与默认行为对比**

```
输入文件: examples/blanks.csv
  a,b,c,d,e,f
  ,NA,N/A,NONE,NULL,.

无 --blanks:
  所有值 → None
  JSON 输出: {"a": null, "b": null, "c": null, ...}
  SQL 类型: BOOLEAN (所有值都是 NULL，默认类型)

有 --blanks:
  null_values = []
  值保持原样: "", "NA", "N/A", "NONE", "NULL", "."
  JSON 输出: {"a": "", "b": "NA", "c": "N/A", ...}
  SQL 类型: VARCHAR NOT NULL (所有值都是非空字符串)
```

**测试2: `--null-value` 追加行为**

```
输入:
  a,b
  n/a,\N

参数: --null-value '\N'

null_values = DEFAULT_NULL_VALUES + ['\\N']
           = ["", "na", "n/a", "none", "null", ".", "\\N"]

结果:
  "n/a" → None (在默认列表中)
  "\\N" → None (在自定义列表中)
  输出: ,  (两列都是 NULL)
```

**测试3: `--blanks` + `--null-value` 组合**

```
输入:
  a,b
  n/a,\N

参数: --blanks --null-value '\\N'

--blanks 先执行: null_values = []
--null-value 后执行: null_values = ['\\N']

结果:
  "n/a" → "n/a" (不在 ['\\N'] 中)
  "\\N" → None (在列表中)
  输出: n/a,  (a 列保持原样，b 列为 NULL)
```

---

## 7. 关键代码位置速查

| 功能 | 文件路径 | 行号 |
|------|----------|------|
| DEFAULT_NULL_VALUES 导入 | `csvkit/cli.py` | 20 |
| null_values 构建逻辑 | `csvkit/cli.py` | 352-358 |
| 类型传递 null_values | `csvkit/cli.py` | 360-387 |
| `--null-value` 参数定义 | `csvkit/cli.py` | 221-223 |
| `--blanks` 参数定义 | `csvkit/cli.py` | 218-220 |
| 测试 `--null-value` | `tests/test_utilities/test_in2csv.py` | 71-91 |
| 测试 `--blanks` JSON 输出 | `tests/test_utilities/test_csvjson.py` | 52-58 |
| 测试 `--blanks` SQL 类型 | `tests/test_utilities/test_csvsql.py` | 100-126 |

---

## 8. 总结

### 8.1 核心要点

1. **DEFAULT_NULL_VALUES 包含**：
   - `""`, `"na"`, `"n/a"`, `"none"`, `"null"`, `"."`
   - 大小写不敏感比较

2. **处理时机**：
   - NULL 候选值**参与**每种类型的识别逻辑
   - 在类型测试时，先检查是否在 `null_values` 中
   - 如果是 NULL 值，所有类型都返回 `True`（视为兼容）
   - **NULL 值不影响类型推断结果**（被跳过）

3. **`--blanks` 的影响**：
   - 将 `null_values` 设置为空列表 `[]`
   - 原先的 NULL 值（`""`, `"NA"`, `"N/A"` 等）被视为普通字符串
   - 这些值会参与类型测试，最终都被推断为 `Text` 类型

4. **`--null-value` 的影响**：
   - **追加**到 `null_values` 列表（不是替换）
   - 对所有类型影响一致：自定义值被视为 NULL
   - 与 `--blanks` 组合时，先清空默认值再追加

### 8.2 实用建议

| 场景 | 推荐参数 |
|------|----------|
| 数据中使用 `"-"` 表示缺失值 | `--null-value "-"` |
| 数据中使用 `"missing"` 表示缺失值 | `--null-value "missing"` |
| 需要保留空字符串作为有效值 | `--blanks` |
| 需要保留 `"N/A"` 作为实际值 | `--blanks` (但会同时影响其他默认 NULL 值) |
| 自定义多个 NULL 值 | `--null-value "?" --null-value "*"` |
| 混合场景：保留 `"N/A"` 但将 `"-"` 视为 NULL | `--blanks --null-value "-"` |

### 8.3 常见陷阱

1. **`--blanks` 是"全有或全无"**：
   - 使用 `--blanks` 会清空**所有**默认 NULL 值
   - 如果只想保留某些默认值，需要用 `--null-value` 重新添加

2. **大小写不敏感**：
   - `"NA"`, `"na"`, `"Na"` 都会匹配 `"na"`
   - 自定义值也是大小写不敏感比较

3. **空字符串 `""` 的特殊性**：
   - 默认情况下 `""` 是 NULL 值
   - 使用 `--blanks` 后 `""` 成为有效值
   - SQL 中 `""` 和 `NULL` 是不同的概念

---

**报告完成时间**：2026-04-29  
**基于版本**：csvkit 2.2.0
