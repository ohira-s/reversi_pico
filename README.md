# reversi_pico
Reversi game with Raspberry Pi PICO and WAVESHARE 3.5 inch Touch-LCD.
Reversi is called as "Othello" in Japan.  So you will see "othello" in file names and program code.

- You neens,
  Raspberry Pi PICO or PICO W
  WAVESHARE 3.5 inch Touch-LCD
  micro python for PICO
  micro puthon development environment (I use Thonny in Raspberry Pi400.)
  
- 4 Game modes
  Man vs CPU
  CPU vs Man
  CPU vs CPU
  Man vs Man

- How to play
  Please read othello.pdf in doc folder.
  
CPU-player uses two cores in PICO as possible to think game strategy.
However in case it fails memory allocation unfortenately, uses main core (core0) only.

CPU-player is still so weak in this version.