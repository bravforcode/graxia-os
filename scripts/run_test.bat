@echo off
cd /d "c:\Users\menum\graxia os"
python scripts\final_test.py > test_output.txt 2>&1
echo Test completed. Check test_output.txt
