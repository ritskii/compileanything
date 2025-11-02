from graphviz import Digraph
from copy import deepcopy
from ir import Var, BinOp, IfStmt, ReturnStmt, PhiNode, BasicBlock


class SSAManager:
    def __init__(self, variables):
        self.counters = {v: 0 for v in variables}
        self.stacks = {v: [] for v in variables}

    def new_name(self, var):
        self.counters[var] += 1
        name = f"{var}{self.counters[var]}"
        self.stacks[var].append(name)
        return name

    def current_name(self, var):
        return self.stacks[var][-1] if self.stacks[var] else f"{var}0"

    def pop_name(self, var):
        if self.stacks[var]:
            self.stacks[var].pop()


class CFG:
    def __init__(self, blocks):
        self.blocks = blocks
        self.start = self.blocks[0]

        self.graph_attr = {'rankdir': 'TB'}
        self.node_attr = {'shape': 'box', 'style': 'filled', 'fillcolor': 'lightgrey'}
        self.edge_attr = {}

        self.dominators = {b: set(self.blocks) for b in self.blocks}
        self.frontiers = {b: set() for b in self.blocks}
        self.variables = set(
            var.name
            for block in self.blocks
            for var in block.instr
            if isinstance(var, Var)
        )

        self.ssa_values = set()
        self.ssa_users = {}

    def compute_dominators(self):
        self.dominators[self.start] = {self.start}
        changed = True
        while changed:
            changed = False
            for block in self.blocks:
                if block == self.start:
                    continue
                if not block.pred:
                    continue
                new_dom = set(self.dominators[block.pred[0]])
                for p in block.pred[1:]:
                    new_dom &= self.dominators[p]
                new_dom.add(block)
                if new_dom != self.dominators[block]:
                    self.dominators[block] = new_dom
                    changed = True

    def get_idom(self):
        idoms = {}
        for block in self.blocks:
            if block == self.start:
                idoms[block] = None
                continue
            doms = self.dominators[block] - {block}
            if not doms:
                idoms[block] = None
                continue
            idoms[block] = min(doms, key=lambda x: len(self.dominators[x]))
        return idoms

    def compute_frontiers(self):
        idoms = self.get_idom()
        for block in self.blocks:
            if len(block.pred) > 1:
                for pred in block.pred:
                    runner = pred
                    while runner != idoms.get(block):
                        self.frontiers[runner].add(block)
                        if runner not in idoms or idoms[runner] is None:
                            break
                        runner = idoms[runner]

    def calculate_phi(self):
        working_list = []
        for var in self.variables:
            for block in self.blocks:
                if block.defined(var):
                    working_list.append(block)
            while working_list:
                defblock = working_list.pop()
                for block in self.frontiers[defblock]:
                    if block.inserted(var):
                        continue
                    block.append_phi(var)
                    working_list.append(block)

    def rename(self):
        ssa_mgr = SSAManager(self.variables)
        idoms = self.get_idom()

        domtree = {b: [] for b in self.blocks}
        for b, idom in idoms.items():
            if idom is not None:
                domtree[idom].append(b)

        def rename_block(block):
            for instr in block.instr:
                if isinstance(instr, PhiNode):
                    newn = ssa_mgr.new_name(instr.name)
                    self.ssa_values.add(newn)
                    instr.name = newn

            for instr in block.instr:
                if isinstance(instr, Var):
                    if isinstance(instr.val, str) and instr.val in ssa_mgr.stacks:
                        instr.val = ssa_mgr.current_name(instr.val)
                    elif isinstance(instr.val, BinOp):
                        if isinstance(instr.val.lhs, str) and instr.val.lhs in ssa_mgr.stacks:
                            instr.val.lhs = ssa_mgr.current_name(instr.val.lhs)
                        if isinstance(instr.val.rhs, str) and instr.val.rhs in ssa_mgr.stacks:
                            instr.val.rhs = ssa_mgr.current_name(instr.val.rhs)
                    instr.name = ssa_mgr.new_name(instr.name)
                    self.ssa_values.add(instr.name)

                elif isinstance(instr, BinOp):
                    if isinstance(instr.lhs, str) and instr.lhs in ssa_mgr.stacks:
                        instr.lhs = ssa_mgr.current_name(instr.lhs)
                    if isinstance(instr.rhs, str) and instr.rhs in ssa_mgr.stacks:
                        instr.rhs = ssa_mgr.current_name(instr.rhs)

                elif isinstance(instr, IfStmt):
                    cond = instr.condition
                    if isinstance(cond, str) and cond in ssa_mgr.stacks:
                        instr.condition = ssa_mgr.current_name(cond)
                    elif isinstance(cond, BinOp):
                        if isinstance(cond.lhs, str) and cond.lhs in ssa_mgr.stacks:
                            cond.lhs = ssa_mgr.current_name(cond.lhs)
                        if isinstance(cond.rhs, str) and cond.rhs in ssa_mgr.stacks:
                            cond.rhs = ssa_mgr.current_name(cond.rhs)

                elif isinstance(instr, ReturnStmt):
                    if instr.base_name in ssa_mgr.stacks:
                        instr.retval = ssa_mgr.current_name(instr.base_name)

            for succ in block.succ:
                for instr in succ.instr:
                    if isinstance(instr, PhiNode):
                        instr.update_incoming(block, ssa_mgr.current_name(instr.name.rstrip("0123456789")))

            for child in domtree[block]:
                rename_block(child)

            for instr in block.instr:
                if isinstance(instr, (Var, PhiNode)):
                    ssa_mgr.pop_name(instr.name.rstrip("0123456789"))

        rename_block(self.start)

    def remove_def(self, value):
        for block in self.blocks:
            for instr in block.instr[:]:
                if isinstance(instr, (Var, BinOp, PhiNode, IfStmt)):
                    if getattr(instr, "name", None) == value:
                        block.instr.remove(instr)
                        print(f"{block.name} removed {len(block.instr)}")
                        return

    def compute_ssa_uses(self):
        self.ssa_users = {v: [] for v in self.ssa_values}

        def visit(val, block, context, instr_ref):
            if isinstance(val, str) and val in self.ssa_values:
                self.ssa_users[val].append(instr_ref)
            elif isinstance(val, BinOp):
                visit(val.lhs, block, f"{context} (lhs)", instr_ref)
                visit(val.rhs, block, f"{context} (rhs)", instr_ref)

        for block in self.blocks:
            for instr in block.instr:
                if isinstance(instr, Var):
                    visit(instr.val, block, f"{instr.name} = ...", instr)
                elif isinstance(instr, BinOp):
                    visit(instr, block, f"{instr.lhs} {instr.op} {instr.rhs}", instr)
                elif isinstance(instr, IfStmt):
                    visit(instr.condition, block, "if ...", instr)
                elif isinstance(instr, ReturnStmt):
                    visit(instr.retval, block, "return ...", instr)
                elif isinstance(instr, PhiNode):
                    for val, pred in instr.incoming:
                        visit(val, block, f"phi({instr.name}) from {pred.name}", instr)

    def is_leaf(self, ssa_name):
        for block in self.blocks:
            for instr in block.instr:
                if getattr(instr, "name", None) == ssa_name:
                    if not isinstance(instr, Var):
                        return False
                    val = instr.val
                    return isinstance(val, (int, float, type(None)))
        return False

    def is_const(self, ssa_name):
        for block in self.blocks:
            for instr in block.instr:
                if getattr(instr, "name", None) == ssa_name:
                    return isinstance(instr, Var) and isinstance(instr.val, (int, float))
        return False

    def get_const(self, ssa_name):
        for block in self.blocks:
            for instr in block.instr:
                if isinstance(instr, Var) and instr.name == ssa_name and isinstance(instr.val, (int, float)):
                    return instr.val
        return None

    def propogate(self, name, value, executable_blocks=None):
        for block in self.blocks:
            if executable_blocks is not None and block not in executable_blocks:
                continue
            for instr in block.instr:
                if instr.replace_uses(name, value):
                    print("test")
                    self.ssa_users[name].remove(instr)


    def render(self, filename="cfg", view=False):
        g = Digraph('CFG', node_attr=self.node_attr, edge_attr=self.edge_attr, graph_attr=self.graph_attr)
        for block in self.blocks:
            g.node(block.name, label=block.get_label())
            for succ in block.succ:
                g.edge(block.name, succ.name)
        if view:
            g.view(filename)
        return g

    def print(self):
        print("=== Control Flow Graph ===")
        for block in self.blocks:
            print(f"\nBlock {block.name}:")
            pred_names = [p.name for p in block.pred]
            succ_names = [s.name for s in block.succ]
            print(f"  Predecessors: {pred_names}")
            print(f"  Successors  : {succ_names}")
            if block.instr:
                print("  Instructions:")
                for instr in block.instr:
                    instr_lines = str(instr).split("\n")
                    for line in instr_lines:
                        print(f"    {line}")
            else:
                print("  (No instructions)")