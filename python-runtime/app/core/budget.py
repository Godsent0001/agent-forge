"""Execution budgets with monotonic deadlines and concurrent-call reservations."""
from __future__ import annotations
import asyncio, threading, time, uuid
from dataclasses import dataclass
from app.contracts.run import BudgetSpec, Totals

class BudgetExceededError(RuntimeError):
    """Raised when an execution resource budget is exhausted."""

@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    estimated_tokens: int = 0

class BudgetTracker:
    """Thread-safe accounting plus preflight reservations for concurrent LLM calls."""
    def __init__(self, spec: BudgetSpec, *, max_parallel_tools: int = 4):
        self.spec=spec
        self._started=time.monotonic()
        self.totals=Totals()
        self._lock=threading.RLock()
        self._reserved_calls: dict[str, BudgetReservation]={}
        self._reserved_tokens=0
        self.tool_semaphore=asyncio.Semaphore(max(1,int(max_parallel_tools)))

    @property
    def elapsed_seconds(self)->float:
        return max(0.0,time.monotonic()-self._started)

    @property
    def remaining_seconds(self)->float|None:
        if self.spec.max_seconds is None: return None
        return max(0.0,float(self.spec.max_seconds)-self.elapsed_seconds)

    def reserve_llm_call(self, *, estimated_tokens:int=0)->BudgetReservation:
        estimated_tokens=max(0,int(estimated_tokens))
        with self._lock:
            self.check_limits()
            inflight=len(self._reserved_calls)
            if self.spec.max_llm_calls is not None and self.totals.llm_calls+inflight>=self.spec.max_llm_calls:
                raise BudgetExceededError(f"LLM call budget exhausted before dispatch ({self.totals.llm_calls+inflight}/{self.spec.max_llm_calls}).")
            if self.spec.max_total_tokens is not None:
                used=self.totals.input_tokens+self.totals.output_tokens+self._reserved_tokens
                if estimated_tokens and used+estimated_tokens>self.spec.max_total_tokens:
                    raise BudgetExceededError(f"Token budget cannot reserve {estimated_tokens} tokens ({used} used/reserved; limit {self.spec.max_total_tokens}).")
            r=BudgetReservation(str(uuid.uuid4()),estimated_tokens)
            self._reserved_calls[r.reservation_id]=r
            self._reserved_tokens+=estimated_tokens
            return r

    def release_reservation(self,reservation:BudgetReservation|None)->None:
        if reservation is None:return
        with self._lock:
            old=self._reserved_calls.pop(reservation.reservation_id,None)
            if old is not None:self._reserved_tokens=max(0,self._reserved_tokens-old.estimated_tokens)

    def record_llm_call(self,input_tokens:int=0,output_tokens:int=0,cache_read_tokens:int=0,cost_usd:float|None=None,*,reservation:BudgetReservation|None=None)->None:
        with self._lock:
            self.release_reservation(reservation)
            self.totals.llm_calls+=1
            self.totals.input_tokens+=max(0,input_tokens)
            self.totals.output_tokens+=max(0,output_tokens)
            self.totals.cache_read_tokens+=max(0,cache_read_tokens)
            if cost_usd is not None:self.totals.cost_usd=(self.totals.cost_usd or 0.0)+max(0.0,cost_usd)
            self.check_limits()

    def record_tool_call(self)->None:
        with self._lock:
            self.totals.tool_calls+=1
            self.check_limits()

    def check_limits(self)->None:
        calls=self.totals.llm_calls+len(self._reserved_calls)
        if self.spec.max_llm_calls is not None and calls>self.spec.max_llm_calls:
            raise BudgetExceededError(f"LLM call count budget exceeded ({calls}>{self.spec.max_llm_calls})")
        tokens=self.totals.input_tokens+self.totals.output_tokens+self._reserved_tokens
        if self.spec.max_total_tokens is not None and tokens>self.spec.max_total_tokens:
            raise BudgetExceededError(f"Token count budget exceeded ({tokens}>{self.spec.max_total_tokens})")
        if self.spec.max_cost_usd is not None and self.totals.cost_usd is not None and self.totals.cost_usd>self.spec.max_cost_usd:
            raise BudgetExceededError(f"Cost budget exceeded (${self.totals.cost_usd:.4f}>${self.spec.max_cost_usd:.4f})")
        if self.spec.max_seconds is not None and self.elapsed_seconds>=self.spec.max_seconds:
            raise BudgetExceededError(f"Time budget exceeded ({self.elapsed_seconds:.1f}s>={self.spec.max_seconds}s)")
