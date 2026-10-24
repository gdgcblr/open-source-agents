from dataclasses import dataclass
@dataclass
class MemoryRecord:
    value:str
    confidence:float
    trust:str
    provenance:str
