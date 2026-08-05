import sys
print(f"Python: {sys.version}")
try:
    import numpy
    print(f"numpy: {numpy.__version__}")
except ImportError:
    print("numpy: MISSING")
try:
    import pandas
    print(f"pandas: {pandas.__version__}")
except ImportError:
    print("pandas: MISSING")
try:
    import scipy
    print(f"scipy: {scipy.__version__}")
except ImportError:
    print("scipy: MISSING")
try:
    import statsmodels
    print(f"statsmodels: {statsmodels.__version__}")
except ImportError:
    print("statsmodels: MISSING")