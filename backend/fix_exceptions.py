import os
import re

def fix_silent_exceptions(directory):
    count = 0
    # Match: except Exception: followed by optional whitespace and 'pass' or 'return None' or 'return {}' or 'return []'
    # and nothing else in that block.
    # We will just look for `except Exception:` and see if the next line is `pass` or `return` without a logging call.
    for root, _, files in os.walk(directory):
        for file in files:
            if not file.endswith('.py'):
                continue
            filepath = os.path.join(root, file)
            with open(filepath, 'r') as f:
                content = f.read()

            # We will use regex to find `except Exception:` followed by spaces and a simple statement.
            # It's better to find `except Exception:` that doesn't have `as e:` and replace it with `except Exception as e:` and add a log.
            # But we must be careful not to break indentation.

            lines = content.split('\n')
            modified = False
            for i, line in enumerate(lines):
                if 'except Exception:' in line:
                    indent = line[:len(line) - len(line.lstrip())]
                    
                    # Check what the next lines are
                    if i + 1 < len(lines):
                        next_line = lines[i+1].strip()
                        if next_line in ('pass', 'return None', 'return {}', 'return []', 'continue', 'break') or next_line.startswith('return '):
                            # It's a silent catch!
                            # Let's replace `except Exception:` with `except Exception as e:`
                            lines[i] = line.replace('except Exception:', 'except Exception as e:')
                            # insert logging
                            log_line = indent + '    import logging; logging.getLogger(__name__).warning("Suppressed exception: %s", e)'
                            lines.insert(i+1, log_line)
                            modified = True
                            count += 1

            if modified:
                with open(filepath, 'w') as f:
                    f.write('\n'.join(lines))
    print(f"Fixed {count} silent exceptions.")

if __name__ == '__main__':
    fix_silent_exceptions('app')
