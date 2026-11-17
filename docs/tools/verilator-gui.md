# Verilator GUI

Open **Verilator GUI** on the desktop. It opens in its own window.

- **File browser (left):** click a folder to go into it, `.. (up)` to go back, or type a path and press Enter.
- **Editor:** click a file to open it in a tab. `Ctrl+S` saves. **New file** makes a file in the current folder.
- **Run:** saves every open file, builds the whole folder with Verilator, and runs the testbench
  (the module whose name starts with `tb` is picked automatically; you can change it).
- **Result badge:** green PASS, red FAIL, or red BUILD ERROR. Errors are listed under **Problems**;
  click one to jump to the line.
- **Waveform:** opens in a pop-up after each run. Zoom with `+`, `-` and **Fit**. Move the mouse over it to
  see every signal's value at the cursor; click to freeze the cursor, click again to release it.
  **Export PNG** saves `waveform.png` into the `work` folder.

It starts in `work/verilog_examples`, an example design with a self-checking testbench.
Files saved in `work` stay on your computer.
