from ir import Var, BinOp, IfStmt, ReturnStmt, PhiNode, BasicBlock, GotoStmt

class PassManager:
    def __init__(self, cfg):
        self.graph = cfg
        self.values = cfg.ssa_values
        self.users = cfg.ssa_users

    def init_lattice(self, graph):
        lattice = {}
        for val in graph.ssa_values:
            if graph.is_const(val):
                lattice[val] = graph.get_const(val)
            else:
                lattice[val] = "top"
        return lattice

    def dce(self, graph):
        use_map = {value: len(users) for value, users in self.users.items()}

        dead = set()
        changed = True

        while changed:
            changed = False
            for value, count in use_map.items():
                if count == 0 and value not in dead:
                    dead.add(value)
                    changed = True
                    for key, user_list in self.users.items():
                        new_list = []
                        for instr in user_list:
                            if getattr(instr, "uses", None) and value in instr.uses():
                                use_map[key] -= 1
                                new_list.append(instr)
                            else:
                                new_list.append(instr)
                        self.users[key] = new_list

        for value in dead:
            graph.remove_def(value)

    def eval_expr(self, expr, lattice):
        if isinstance(expr, (int, float)):
            return expr
        elif isinstance(expr, str):
            val = lattice.get(expr, "top")
            return val if val is not None else "top"
        elif isinstance(expr, BinOp):
            lhs = self.eval_expr(expr.lhs, lattice)
            rhs = self.eval_expr(expr.rhs, lattice)
            if lhs == "top" or rhs == "top":
                return "top"
            try:
                if expr.op == '+':
                    return lhs + rhs
                elif expr.op == '-':
                    return lhs - rhs
                elif expr.op == '*':
                    return lhs * rhs
                elif expr.op == '/':
                    return lhs / rhs if rhs != 0 else "top"
                elif expr.op == '<':
                    return int(lhs < rhs)
                elif expr.op == '>':
                    return int(lhs > rhs)
                elif expr.op == '==':
                    return int(lhs == rhs)
                elif expr.op == '!=':
                    return int(lhs != rhs)
                else:
                    return "top"
            except:
                return "top"
        else:
            return "top"

    def replace_phi_with_const(self, blocks, lattice, executable_blocks):
        for block in blocks:
            new_instr = []
            for instr in block.instr:
                if isinstance(instr, PhiNode):
                    const_vals = set()
                    for val, pred in instr.incoming:
                        if pred in executable_blocks:
                            const_vals.add(lattice[val] if isinstance(val, str) else val)
                    if len(const_vals) == 1:
                        const_val = const_vals.pop()
                        new_instr.append(Var(instr.name, const_val))
                        for b in blocks:
                            for u in b.instr:
                                u.replace_uses(instr.name, const_val)
                    else:
                        new_instr.append(instr)
                else:
                    new_instr.append(instr)
            block.instr = new_instr

    def sccp(self, graph):
        lattice = self.init_lattice(graph)
        executable_blocks = set()
        worklist_blocks = [graph.start]
        worklist_values = list(lattice.keys())

        while worklist_blocks or worklist_values:
            while worklist_blocks:
                block = worklist_blocks.pop()
                if block in executable_blocks:
                    continue
                executable_blocks.add(block)

                for instr in block.instr:
                    if isinstance(instr, Var):
                        val = instr.val
                        if isinstance(val, (int, float)):
                            lattice[instr.name] = val
                        elif isinstance(val, str) and lattice.get(val) not in ("top", None):
                            lattice[instr.name] = lattice[val]
                        elif isinstance(val, BinOp):
                            lhs = lattice[val.lhs] if isinstance(val.lhs, str) else val.lhs
                            rhs = lattice[val.rhs] if isinstance(val.rhs, str) else val.rhs
                            if isinstance(lhs, (int, float)) and isinstance(rhs, (int, float)):
                                if val.op == '+':
                                    lattice[instr.name] = lhs + rhs
                                elif val.op == '-':
                                    lattice[instr.name] = lhs - rhs
                                elif val.op == '*':
                                    lattice[instr.name] = lhs * rhs
                                elif val.op == '/':
                                    lattice[instr.name] = lhs / rhs if rhs != 0 else "top"
                                else:
                                    lattice[instr.name] = "top"
                            else:
                                lattice[instr.name] = "top"



                    elif isinstance(instr, PhiNode):

                        const_vals = set()

                        for val, pred in instr.incoming:
                            if pred not in executable_blocks:
                                continue

                            v = lattice[val] if isinstance(val, str) else val

                            if v != "top" and v is not None:
                                const_vals.add(v)

                        if len(const_vals) == 1:

                            lattice[instr.name] = const_vals.pop()

                        elif len(const_vals) == 0:

                            lattice[instr.name] = "top"

                        else:

                            lattice[instr.name] = "top"



                    elif isinstance(instr, IfStmt):
                        name_to_block = {b.name: b for b in graph.blocks}

                        then_block = name_to_block[instr.thengoto.goto]
                        else_block = name_to_block[instr.elsegoto.goto]

                        cond_val = self.eval_expr(instr.condition, lattice)
                        if cond_val == 1:
                            worklist_blocks.append(then_block)
                        elif cond_val == 0: 
                            worklist_blocks.append(else_block)
                        else:
                            if then_block not in executable_blocks:
                                worklist_blocks.append(then_block)
                            if else_block not in executable_blocks:
                                worklist_blocks.append(else_block)

                    elif isinstance(instr, GotoStmt):
                        name_to_block = {b.name: b for b in graph.blocks}
                        target_block = name_to_block[instr.goto]
                        if target_block not in executable_blocks:
                            worklist_blocks.append(target_block)

            while worklist_values:
                val = worklist_values.pop()
                graph.propogate(val, lattice[val], executable_blocks)
                for user_instr in graph.ssa_users.get(val, []):
                    block = next(b for b in graph.blocks if user_instr in b.instr)
                    if block in executable_blocks:
                        worklist_blocks.append(block)

        self.replace_phi_with_const(graph.blocks, lattice, executable_blocks)
