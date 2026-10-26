"""
Minimal local stand-in for the `genlayer` SDK so the contract logic can be
unit-tested without GenLayer Studio. It simulates:
  - storage fields (TreeMap / DynArray / u256 auto-initialised)
  - gl.public.write / gl.public.view decorators
  - gl.message.sender_address
  - gl.nondet.web.render / gl.nondet.exec_prompt (scripted responses)
  - gl.vm.run_nondet_unsafe (leader runs, then ONE validator re-runs and votes)

This is NOT a consensus simulator. Final verification must be done in
GenLayer Studio (see README).
"""
import sys
import types
import typing


class TreeMap(dict):
    pass


class DynArray(list):
    pass


u256 = int


class Address:
    def __init__(self, hex_str):
        self.as_hex = hex_str


class Return:
    def __init__(self, calldata):
        self.calldata = calldata


class Contract:
    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        for klass in reversed(cls.__mro__):
            for name, ann in getattr(klass, "__annotations__", {}).items():
                origin = typing.get_origin(ann) or ann
                try:
                    obj.__dict__[name] = origin()
                except Exception:
                    obj.__dict__[name] = None
        return obj


class _Public:
    @staticmethod
    def write(fn):
        return fn

    @staticmethod
    def view(fn):
        return fn


class _Message:
    sender_address = Address("0xHOLDER")


class _Web:
    pages = []          # queue of page texts (or Exception instances)

    @classmethod
    def render(cls, url, mode="text"):
        item = cls.pages.pop(0) if len(cls.pages) > 1 else cls.pages[0]
        if isinstance(item, Exception):
            raise item
        return item


class _Nondet:
    web = _Web
    llm_queue = []      # one raw LLM answer per call (leader first, then validator)

    @classmethod
    def exec_prompt(cls, prompt):
        return cls.llm_queue.pop(0)


class _Vm:
    Return = Return
    validator_accepts_log = []

    @staticmethod
    def run_nondet_unsafe(leader_fn, validator_fn):
        leader_value = leader_fn()
        ok = validator_fn(Return(leader_value))
        _Vm.validator_accepts_log.append(ok)
        if not ok:
            raise Exception("Consensus failed: validator rejected leader result")
        return leader_value


class _GL:
    Contract = Contract
    public = _Public
    message = _Message
    nondet = _Nondet
    vm = _Vm


gl = _GL


def install():
    mod = types.ModuleType("genlayer")
    mod.gl = gl
    mod.TreeMap = TreeMap
    mod.DynArray = DynArray
    mod.u256 = u256
    sys.modules["genlayer"] = mod
    return gl


def reset():
    _Message.sender_address = Address("0xHOLDER")
    _Web.pages = ["Some page text"]
    _Nondet.llm_queue = []
    _Vm.validator_accepts_log = []
