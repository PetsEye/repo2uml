"""Parser package: stdlib static analysis per language."""
from .base import ModuleInfo
from .python_p import parse_python
from .typescript_p import parse_typescript
from .go_p import parse_go
from .java_p import parse_java
from .kotlin_p import parse_kotlin
from .schema_p import parse_proto, parse_prisma

__all__ = ["ModuleInfo", "parse_python", "parse_typescript", "parse_go",
           "parse_java", "parse_kotlin", "parse_proto", "parse_prisma"]
