"""具体格式解析器：文档/表格/PPT/PDF 与 图片/录音。

它们 import 时把自己登记进 `backend.parse.base.REGISTRY`，所以这里做副作用导入；
调用方一律走 `backend.parse` 的门面，不该直接引到这一层来挑解析器。
"""

from backend.parse.parsers import documents, media  # noqa: F401
