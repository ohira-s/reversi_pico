# reversi_pico
Reversi game with Raspberry Pi PICO and WAVESHARE 3.5 inch Touch-LCD.
Reversi is called as "Othello" in Japan.  So you will see "othello" in file names and program code.

- You neens,
  Raspberry Pi PICO or PICO W (WiFi is not used)
  WAVESHARE 3.5 inch Touch-LCD
  micro python for PICO
  micro python development environment (I use Thonny in Raspberry Pi400.)
  
- 4 Game modes
  Man vs CPU (MC)
  CPU vs Man (CM)
  CPU vs CPU (CC)
  Man vs Man (MM)

- How to play
  Please read othello.pdf in doc folder.
  
CPU-player uses two cores in PICO as possible to think game strategy.
However in case it fails memory allocation unfortenately, uses main core (core0) only.
Two CPU cores get next turn's candidates by Generator-Yield pattern.  So they works very efficiently.

CPU-player is still weak in this version.
