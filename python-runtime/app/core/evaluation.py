"""Deterministic result aggregation for agent-core regression evaluations."""
from dataclasses import dataclass,field
from statistics import mean

@dataclass
class EvaluationCaseResult:
    case_id:str
    passed:bool
    duration_seconds:float=0.0
    cost_usd:float|None=None
    tokens:int=0
    failure_category:str|None=None

@dataclass
class EvaluationReport:
    results:list[EvaluationCaseResult]=field(default_factory=list)
    @property
    def total(self):return len(self.results)
    @property
    def pass_rate(self):return sum(r.passed for r in self.results)/self.total if self.total else 0.0
    @property
    def mean_duration_seconds(self):return mean(r.duration_seconds for r in self.results) if self.results else 0.0
    @property
    def total_tokens(self):return sum(max(0,r.tokens) for r in self.results)
    @property
    def known_total_cost_usd(self):
        return None if not self.results or any(r.cost_usd is None for r in self.results) else sum(max(0.0,r.cost_usd or 0.0) for r in self.results)
    def summary(self):
        failures={}
        for r in self.results:
            if not r.passed:
                k=r.failure_category or "unspecified";failures[k]=failures.get(k,0)+1
        return {"total":self.total,"passed":sum(r.passed for r in self.results),"pass_rate":self.pass_rate,
                "mean_duration_seconds":self.mean_duration_seconds,"total_tokens":self.total_tokens,
                "known_total_cost_usd":self.known_total_cost_usd,"failure_categories":failures}
