# Record with: vhs docs/demo.tape   (https://github.com/charmbracelet/vhs)
Output docs/demo.gif
Set FontSize 16
Set Width 1200
Set Height 750
Set Theme "Dracula"

Type "cat samples/typo_and_division.py"
Enter
Sleep 3s
Type "autofix samples/typo_and_division.py --no-diff"
Enter
Sleep 6s
Type "autofix samples/typo_and_division.py -o /tmp/fixed.py > /dev/null && python /tmp/fixed.py"
Enter
Sleep 3s
