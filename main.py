import sys
from ir import *
from cfg import CFG
from passes import PassManager
from parser import parse_file


def process_file(filename):    
    cfg = parse_file(filename)
    
    cfg.compute_dominators()
    cfg.compute_frontiers()
    cfg.calculate_phi()
    cfg.rename()
    cfg.compute_ssa_uses()
    
    pm = PassManager(cfg)
    pm.sccp(cfg)
    pm.dce(cfg)
    cfg.print()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = 'test.ir'
    
    try:
        process_file(filename)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        print("Usage: python main.py [filename]")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)