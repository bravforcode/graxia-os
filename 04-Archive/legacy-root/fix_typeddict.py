import os
import re

for root, dirs, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'TypedDict' in content and 'from typing import' in content:
                # Add from typing_extensions import TypedDict
                if 'from typing_extensions import TypedDict' not in content:
                    content = content.replace('from typing import', 'from typing_extensions import TypedDict\nfrom typing import')
                
                # Remove TypedDict from typing import
                content = re.sub(r'from typing import(.*?)\bTypedDict\b,?', r'from typing import\1', content)
                content = content.replace('from typing import \n', 'from typing import ')
                content = content.replace('from typing import  ', 'from typing import ')
                
                # Cleanup empty trailing commas
                content = re.sub(r'from typing import\s*,', 'from typing import ', content)
                content = re.sub(r'from typing import(.*?),\s*\n', r'from typing import\1\n', content)
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
