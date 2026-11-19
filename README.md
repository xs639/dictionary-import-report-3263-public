# 字典导入校验报告

需要 Python 3.11 或更新版本。运行只使用 Python 标准库。示例是虚构的。执行测试前需要安装 pytest。

```shell
python import_report.py example-import.csv example-snapshot.csv sample-output
python -m pip install pytest
python -m pytest -q
```

`import-report.html` 包含汇总、错误、冲突和疑似重复四部分。错误和冲突按源 CSV 记录号定位，同一条记录在汇总中只计一种处理结果。按编码识别新增、更新和无变化。批次中的重复编码作为冲突列出。

疑似重复按名称相似度或别名交集判定。相似度严格大于 0.85 或有相同别名才列出。疑似重复供人工核对，脚本不会自动合并。

`retry-import.csv` 继承源 CSV 的表头、列顺序和值，以带 BOM 的 UTF-8 写出。编辑错误或冲突记录后，可用同一读入程序重新校验。示例契约要求 `code`、`name`、`aliases` 三列，别名用 `|` 分隔。集成时可以调用 `generate(import_path, snapshot_path, out_dir, columns=Columns(...))` 配置实际列名与别名分隔符，也可以把导入数据与现有字典快照传给 `validate_import`。回导测试使用示例契约及自定义列契约。接入客户系统时应对照其正式表头和回导接口。

## 验收文件

两份输入分别为 `example-import.csv` 与 `example-snapshot.csv`。用浏览器打开 `sample-output/import-report.html` 可核对四个报告区及三对疑似重复。可回导的原始 CSV 为 `sample-output/retry-import.csv`，修正样例 `sample-output/retry-corrected.csv` 仅补上编码 MISSING 对应的名称。

```shell
python import_report.py sample-output/retry-corrected.csv example-snapshot.csv corrected-output
python -m pytest -q test_import_report.py
```

修正后的 `corrected-output/import-report.html` 显示新增 5 条、更新 1 条、冲突 2 条、错误 0 条，三对疑似重复仍可见。`test_import_report.py` 内包含四区、三对名称、阈值与别名、CSV 编辑回导的断言。`pytest-output.txt` 保存实测输出。
