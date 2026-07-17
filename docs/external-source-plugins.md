# RouteCollector external source plugin

External source packages register plugins through Python entry points.

## Minimal plugin

```python
from routecollector.sources.base import (
    DomainSource,
    DomainSourceRequest,
    DomainSourceResult,
)


class ExampleSource(DomainSource):
    @property
    def name(self) -> str:
        return "example"

    def load(
        self,
        request: DomainSourceRequest,
    ) -> DomainSourceResult:
        return DomainSourceResult(
            source_name=self.name,
            service_name=request.service_name,
            domains=self.normalize_domains(
                ["example.com"]
            ),
        )
```

## pyproject.toml

```toml
[project]
name = "routecollector-source-example"
version = "0.1.0"
dependencies = [
    "routecollector>=1.2.0",
]

[project.entry-points."routecollector.sources"]
example = "routecollector_source_example:ExampleSource"
```

The entry-point name must exactly match `ExampleSource.name`.

After installing the package into the same Python virtual environment as
RouteCollector, it appears automatically in:

```bash
routecollector sources
```

and can be used in a service YAML:

```yaml
sources:
  - type: example
```
