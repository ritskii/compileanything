class Node:
    def __init__(self, name=None):
        self.name = name

    def replace_uses(self, name, value):
        return False


class Var(Node):
    def __init__(self, name, val):
        super().__init__(name)
        self.val = val

    def __repr__(self):
        return f"{self.name}={self.val}"

    def replace_uses(self, name, value):
        changed = False
        if isinstance(self.val, str) and self.val == name:
            self.val = value
            changed = True
        elif isinstance(self.val, Node):
            changed = self.val.replace_uses(name, value)
        return changed


class BinOp(Node):
    def __init__(self, lhs, rhs, op):
        super().__init__(None)
        self.lhs = lhs
        self.rhs = rhs
        self.op = op

    def __repr__(self):
        return f"{self.lhs} {self.op} {self.rhs}"

    def replace_uses(self, name, value):
        changed = False
        if isinstance(self.lhs, str) and self.lhs == name:
            self.lhs = value
            changed = True
        elif isinstance(self.lhs, Node):
            changed |= self.lhs.replace_uses(name, value)
        if isinstance(self.rhs, str) and self.rhs == name:
            self.rhs = value
            changed = True
        elif isinstance(self.rhs, Node):
            changed |= self.rhs.replace_uses(name, value)
        return changed


class IfStmt(Node):
    def __init__(self, condition, thengoto, elsegoto):
        super().__init__(None)
        self.condition = condition
        self.thengoto = thengoto
        self.elsegoto = elsegoto

    def __repr__(self):
        return f"if({self.condition}) {self.thengoto}\nelse {self.elsegoto}"

    def replace_uses(self, name, value):
        changed = False
        if isinstance(self.condition, str) and self.condition == name:
            self.condition = value
            changed = True
        elif isinstance(self.condition, Node):
            changed = self.condition.replace_uses(name, value)
        return changed

class ReturnStmt(Node):
    def __init__(self, base_name):
        super().__init__(base_name)
        self.base_name = base_name
        self.retval = base_name

    def __repr__(self):
        return f"return {self.retval}"

    def replace_uses(self, name, value):
        changed = False
        if isinstance(self.retval, str) and self.retval == name:
            self.retval = value
            changed = True
        elif isinstance(self.retval, Node):
            changed = self.retval.replace_uses(name, value)
        return changed


class GotoStmt(Node):
    def __init__(self, goto):
        super().__init__(None)
        self.goto = goto

    def __repr__(self):
        return f"goto {self.goto}"

    def replace_uses(self, name, value):
        changed = False
        if isinstance(self.goto, str) and self.goto == name:
            self.goto = value
            changed = True
        elif isinstance(self.goto, Node):
            changed = self.goto.replace_uses(name, value)
        return changed


class PhiNode(Node):
    def __init__(self, var):
        super().__init__(var)
        self.name = var
        self.incoming = []

    def add_incoming(self, value, pred):
        self.incoming.append((value, pred))

    def update_incoming(self, pred, value):
        for i, (v, p) in enumerate(self.incoming):
            if p == pred:
                self.incoming[i] = (value, p)

    def __repr__(self):
        incomings = ', '.join(f"{v}@{p.name}" for v, p in self.incoming)
        return f"{self.name} = phi({incomings})"

    def replace_uses(self, name, value):
        changed = False
        for i, (v, p) in enumerate(self.incoming):
            if isinstance(v, str) and v == name:
                self.incoming[i] = (value, p)
                changed = True
            elif isinstance(v, Node):
                changed |= v.replace_uses(name, value)
        return changed


class BasicBlock(Node):
    def __init__(self, name, instr=None):
        super().__init__(name)
        self.instr = instr or []
        self.pred = []
        self.succ = []
        self.variables = set(stmt.name for stmt in self.instr if isinstance(stmt, Var))

    def __repr__(self):
        instr_str = "\n ".join(str(i) for i in self.instr)
        return f"{self.name}:\n {instr_str}"

    def defined(self, var):
        return any(isinstance(instr, Var) and instr.name == var for instr in self.instr)

    def inserted(self, var):
        return any(isinstance(instr, PhiNode) and instr.name == var for instr in self.instr)

    def append_phi(self, var):
        phi = PhiNode(var)
        for pred in self.pred:
            phi.add_incoming("undef", pred)
        self.instr.insert(0, phi)

    def add_pred(self, *blocks):
        self.pred.extend(blocks)

    def add_succ(self, *blocks):
        self.succ.extend(blocks)

    def get_label(self):
        instr_str = "\n".join(str(i) for i in self.instr)
        return f"{self.name}:\n{instr_str}"