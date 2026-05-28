import os

def fix_logging(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if not file.endswith('.py'):
                continue
            filepath = os.path.join(root, file)
            with open(filepath, 'r') as f:
                content = f.read()

            if 'import logging; logging.getLogger' in content:
                # Remove the inline import
                content = content.replace('import logging; logging.getLogger', 'logging.getLogger')
                
                # Ensure import logging is at the top
                if 'import logging' not in content:
                    # insert after first docstring or just at top
                    lines = content.split('\n')
                    # just put it at line 0 for simplicity if not present
                    lines.insert(0, 'import logging')
                    content = '\n'.join(lines)
                
                with open(filepath, 'w') as f:
                    f.write(content)
                print(f"Fixed {filepath}")

if __name__ == '__main__':
    fix_logging('app')
