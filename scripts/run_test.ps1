cd "c:\Users\menum\graxia os"
$env:PYTHONPATH = "backend;$env:PYTHONPATH"
python scripts\final_test.py 2>&1 | Tee-Object -FilePath "test_output.txt"
