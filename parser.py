import re
from ir import Var, BinOp, IfStmt, ReturnStmt, GotoStmt, BasicBlock
from cfg import CFG


class Parser:
    def __init__(self, code):
        self.code = code
        self.tokens = []
        self.pos = 0
        self.block_counter = 0
        
    def tokenize(self):
        patterns = [
            (r'\bvar\b', 'VAR'),
            (r'\bif\b', 'IF'),
            (r'\belse\b', 'ELSE'),
            (r'\breturn\b', 'RETURN'),
            (r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', 'IDENTIFIER'),
            (r'\d+', 'NUMBER'),
            (r'[+\-*/<>]=?|=', 'OPERATOR'),
            (r'[{}();]', 'PUNCTUATION'),
        ]
        
        regex = '|'.join(f'({pattern})' for pattern, _ in patterns)
        
        self.tokens = []
        for match in re.finditer(regex, self.code):
            token_type = None
            for i, (pattern, ttype) in enumerate(patterns):
                if match.group(i + 1):
                    token_type = ttype
                    break
            
            if token_type:
                value = match.group(0)
                if not value.strip():
                    continue
                self.tokens.append((token_type, value.strip()))
        
        self.tokens.append(('EOF', None))
        
    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return ('EOF', None)
    
    def consume(self, expected_type=None):
        if self.pos >= len(self.tokens):
            return ('EOF', None)
        token = self.tokens[self.pos]
        if expected_type and token[0] != expected_type:
            raise SyntaxError(f"Expected {expected_type}, got {token[0]}")
        self.pos += 1
        return token
    
    def expect(self, token_type):
        token = self.consume()
        if token[0] != token_type:
            raise SyntaxError(f"Expected {token_type}, got {token[0]}")
        return token
    
    def new_block_name(self):
        name = f"bb{self.block_counter}"
        self.block_counter += 1
        return name
    
    def parse_expression(self):
        token_type, value = self.peek()
        
        if token_type == 'NUMBER':
            self.consume()
            lhs = int(value)
        elif token_type == 'IDENTIFIER':
            self.consume()
            lhs = value
        else:
            raise SyntaxError(f"Unexpected token in expression: {token_type}")
        
        if self.peek()[0] == 'OPERATOR' and self.peek()[1] != '=':
            op_token = self.consume('OPERATOR')
            op = op_token[1]
            rhs = self.parse_expression()
            return BinOp(lhs, rhs, op)
        
        return lhs
    
    def parse_var_decl(self):
        self.expect('VAR')
        name_token = self.expect('IDENTIFIER')
        var_name = name_token[1]
        self.expect('OPERATOR')  # '='
        value = self.parse_expression()
        return Var(var_name, value)
    
    def parse_if_statement(self):
        self.expect('IF')
        self.expect('PUNCTUATION')  # '('
        
        condition = self.parse_expression()
        self.expect('PUNCTUATION')  # ')'
        self.expect('PUNCTUATION')  # '{'
        
        then_block = BasicBlock(self.new_block_name(), [])
        else_block = BasicBlock(self.new_block_name(), [])
        merge_block = BasicBlock(self.new_block_name(), [])
        
        then_instrs = []
        while self.peek()[0] != 'PUNCTUATION' or self.peek()[1] != '}':
            if self.peek()[0] == 'VAR':
                then_instrs.append(self.parse_var_decl())
                if self.peek()[0] == 'PUNCTUATION' and self.peek()[1] == ';':
                    self.consume()
            else:
                break
        then_block.instr = then_instrs
        if then_block.instr:
            then_block.variables = set(stmt.name for stmt in then_block.instr if isinstance(stmt, Var))
        then_block.add_succ(merge_block)
        then_block.instr.append(GotoStmt(merge_block.name))
        
        self.expect('PUNCTUATION')  # '}'
        self.expect('ELSE')
        self.expect('PUNCTUATION')  # '{'
        
        else_instrs = []
        while self.peek()[0] != 'PUNCTUATION' or self.peek()[1] != '}':
            if self.peek()[0] == 'VAR':
                else_instrs.append(self.parse_var_decl())
                if self.peek()[0] == 'PUNCTUATION' and self.peek()[1] == ';':
                    self.consume()
            else:
                break
        else_block.instr = else_instrs
        if else_block.instr:
            else_block.variables = set(stmt.name for stmt in else_block.instr if isinstance(stmt, Var))
        else_block.add_succ(merge_block)
        else_block.instr.append(GotoStmt(merge_block.name))
        
        self.expect('PUNCTUATION')  # '}'
        
        if_block = BasicBlock(self.new_block_name(), [
            IfStmt(condition, GotoStmt(then_block.name), GotoStmt(else_block.name))
        ])
        if_block.add_succ(then_block, else_block)
        
        return if_block, then_block, else_block, merge_block
    
    def parse_return(self):
        self.expect('RETURN')
        name_token = self.expect('IDENTIFIER')
        return ReturnStmt(name_token[1])
    
    def parse(self):
        self.tokenize()
        
        blocks = []
        current_block = BasicBlock(self.new_block_name(), [])
        blocks.append(current_block)
        
        while self.peek()[0] != 'EOF':
            token_type, value = self.peek()
            
            if token_type == 'VAR':
                instr = self.parse_var_decl()
                current_block.instr.append(instr)
                current_block.variables.add(instr.name)
                # Consume semicolon if present
                if self.peek()[0] == 'PUNCTUATION' and self.peek()[1] == ';':
                    self.consume()
                    
            elif token_type == 'IF':
                prev_block = current_block
                
                if_block, then_block, else_block, merge_block = self.parse_if_statement()
                
                prev_block.add_succ(if_block)
                if_block.add_pred(prev_block)
                prev_block.instr.append(GotoStmt(if_block.name))
                
                blocks.extend([if_block, then_block, else_block])
                
                # Set up predecessors
                then_block.add_pred(if_block)
                else_block.add_pred(if_block)
                merge_block.add_pred(then_block, else_block)
                
                current_block = merge_block
                blocks.append(merge_block)
                
            elif token_type == 'RETURN':
                instr = self.parse_return()
                current_block.instr.append(instr)
                break
            else:
                self.consume()
        
        return CFG(blocks)


def parse_file(filename):
    with open(filename, 'r') as f:
        code = f.read()
    parser = Parser(code)
    return parser.parse()
