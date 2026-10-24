<!-- Paste into AGENTS.md, CLAUDE.md, .cursorrules or your agent's rules file. Requires `pipx install git+https://github.com/mrzroot/vazhgun`. -->

## Persian (Farsi) Word documents: direction and number order

Do not assume that a Persian paragraph in a `.docx` is right-to-left because it is right-aligned, or that `شکل ۲-۳` is drawn as typed. Paragraph direction (`w:bidi`) and table direction (`w:bidiVisual`) are separate properties, and a hyphen or slash between Persian digits is drawn in an order that depends on the text around it. Before editing or generating a Persian `.docx`, run:

```sh
vazhgun thesis.docx                 # findings with the line as typed and as (approximately) drawn
vazhgun thesis.docx --json          # machine-readable
vazhgun thesis.docx --fix --chains ltr   # writes thesis.vazhgun.docx, never overwrites
```

- Report what it finds; do not silently "fix" number order. Ask which convention the university wants (first number on the left or on the right) and apply it to the whole document.
- It is a Unicode-algorithm preview, not Word. Tell the user to open the result in Word and look at the flagged lines.
- It runs offline, sends nothing anywhere, and reads/writes only the files you give it.
