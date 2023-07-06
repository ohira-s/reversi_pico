'''
# Othello (Reversi) game program for Raspberry Pi PICO
# with Touch LCD display (WAVESHARE Pico-Res Touch-LCD-3.5inch)
#
# This program uses multi-core to think game strategy.
#
# Copyright Shunsuke Ohira, 2023
'''

import time, machine, _thread
import re
import gc

# Interface class for WAVESHARE Pico-Res Touch-LCD-3.5inch
from TouchLCD_3inch5 import TouchLCD_3inch5
    
# PIO:  Periodical IRQ for getting touch data on LCD
import rp2
@rp2.asm_pio()
def pio_clock_irq():
    set(x, 2)                [15]
    label("wait_loop")
    jmp(x_dec, "wait_loop")  [15]
    irq(0)                   [15]


'''
### Othello (Reversi) board class ###
# Class: Retaining the current game strategy and status.
# Main instances:
    othello:    The game board
    undo_board: A game board for undo (retain the previous board)
    turn:       Possible boards in tracing game tree
'''
class Board_class:
    ### Class constant variables ###
    
    # Piece in a board cell
    BLANK = " "     # Blank
    WHITE = "O"     # White
    BLACK = "#"     # Black
    
    # Player type
    white_is_cpu = False
    black_is_cpu = True
    in_play = False
    
    ### Class static variables ###
    
    # Maximum candidates to try putting a piece in next turn
    LIMIT_CANDIDATES = 16
    
    # Thought depth (actual depth = MAX_DEPTH * 2 - 1 (my turn + opponent turn))
    MAX_DEPTH = 2
    
    # EVAL_MODE: Evaluation mode to change evaluation value and algorithm in self.evaluations() etc.
    EVAL_MODE_auto = 0
    EVAL_MODE_pieces = 1
    EVAL_MODE_pieces_inverse = 2
    EVAL_MODE_few_candidates = 3
    EVAL_MODE_many_places = 4
    
    eval_mode = EVAL_MODE_pieces_inverse
    auto_mode = False
    
    # Turn and strategy: turn:[candidates, depth, eval_mode] ,turn must be even number
    strategies = [
        {0:[16,1,2], 8:[16,2,3], 16:[16,4,0], 32:[16,4,1]},
        {0:[16,1,2], 6:[16,2,2], 10:[16,3,3], 22:[16,4,0], 32:[16,4,1]},
        {0:[16,1,0], 8:[16,2,0], 16:[16,4,0]}
    ]
    ''' Stragegy for debug
    strategies = [
        {0:[16,2,1]}
    ]
    '''
    strategy = strategies[0]

    # (x,y): cell placed a piece
    # [sx,sy,dx,dy,[[pattern0,value0],[pattern1,value1],...]]
    # sx,sy: cell to start checking petterns
    # dx,dy: delta x and y to add sx,sy to get cells for checking patterns
    # pattern: W=place color, B=oppornent color, _=blank
    # value: evaluation value for a check,
    #   value > 0: good strategy, equal or more than 999999 means strongly recommended strategy.
    #   value < 0: bad strategy.
    # Program automattically detects a symmetry pattern, so patterns should be defined in x:0..3 andy:0..3 area.
    # DO NOT NEED define both getting a corner pattern and losing a corner pattern (detected by logic)
    critical_case = {
        (0,0):[[0,0, 1,0, 8, [
                                ["^W+_W+_$", -99999],
                                ["^WBW+_W$", -99999],
                                ["^W_W+BW$", -99999]
                              ]
                ],
               [0,0, 0,1, 8, [
                                ["^W+_W+_$", -99999],
                                ["^WBW+_W$", -99999],
                                ["^W_W+BW$", -99999]
                              ]
                ],
               [0,0, 1,1, 8, [
                                ["^W+_W+_$", -99999],
                                ["^WBW+_W$", -99999],
                                ["^W_W+BW$", -99999]
                              ]
                ]
               ],

        (1,0):[[0,0, 1,0, 8, [
                                ["^_W+_W.*$",   -99999],
                                ["^_W+_B+W.*$", -99999],
                                ["^_W+_+B.*$",  111111],
                                ["^_W+__W+_.*$",111111],
                                ["^_W+_+$",     111111],
                              ]
                ]
               ],

        (2,0):[[0,0, 1,0, 8, [
                                ["^_WW+_W.*$",    -99999],
                                ["^_WW+_B+W.*$",  -99999],
                                ["^..W+_W+_$",    -99999],
                                ["^..W+_B+W+_$",  -99999],
                                ["^_BW+_.*$",     -99999],
                                ["^__W+B[B|_]+$", -99999],
                                ["^_BW+B.*$",    1000000],
                                ["^_WW+_+B.*$",   333333],
                                ["^_WW+__W+_.*$", 555555],
                                ["^__W_WW_+$",    555555],
                                ["^__WW_W_+$",    555555],
                                ["^_WW+_+$",      777777]
                              ]
                ]
               ],

        (3,0):[[0,0, 1,0, 8, [
                                ["^_W_W.*",        -99999],
                                ["^_WWW+_W+$",     -99999],
                                ["^_WWW+_B+W.*$",  -99999],
                                ["^...W+_W+_$",    -99999],
                                ["^...W+_B+W+_$",  -99999],
                                ["^___W+B[B|_]+$", -99999],
                                ["^_W_W+B+$",      -99999],
                                ["^__BWBB_+$",     -99999],
                                ["^_BBW+_.*$",     -99999],
                                ["^_WWW+_+B.*$",   333333],
                                ["^_WwW+__W+_.*$", 555555],
                                ["^__WW_W_+$",     555555],
                                ["^_WWW+_+$",      777777],
                                ["^_BBW+B.*$",    1000000]
                              ]
                ]
               ],

        (1,1):[[0,0, 1,1, 8, [
                                ["^_W+_W.*$",   -99999],
                                ["^_W+_B+W.*$", -99999]
                              ],
                ],
               [1,1, 0,0, 1, [
                                ["W",            -9998]
                              ]
                ]
               ],

        (2,2):[[0,0, 1,1, 8, [
                                ["^_WW+_+$",    777777]
                              ],
                ]
               ],

        (3,3):[[0,0, 1,1, 8, [
                                ["^_WWW+_+$",   777777]
                              ],
                ]
               ]
    }

    # Thought program working flag in multi-core
    bg_wakeup = False

    # Make it True to terminate multi-core process
    bg_terminate = False

    # Multi-core process is working or not
    bg_working = False
    
    # Candidates list to let think game strategy in multi-core, otherwize should be always None
    bg_cands = None
    bg_turn_color = 0    # Think the strategy to this turn color

    # A next turn board chosen by multi-core process
    bg_selected_turn = None

    all_cands = 0
    proc_cands = 0
    proc_cands_bg = 0
    
    # Cell touched by GUI just before
    touched_cell = None
    
    # Candidate places evaluating currently (main-core and muti-core), used for only showing them on board
    evaluating_places = [(-1,-1),(-1,-1)]
    
    '''
    # Class instance initialization and instance variables
    '''
    def __init__(self, name):
        self.board_name = name         # Othello board instance name (usefully for debugging)
        self.board = []                # Othello board matrix: " "=blank, "O"=white, "#"=black
    
    '''
    # Restart game
    '''
    def restart(self):
        if len(self.board) == 0:
            for y in list(range(8)):
                self.board.append([" "]* 8)          
        else:
            for y in list(range(8)):
                for x in list(range(8)):
                    self.board[y][x] = Board_class.BLANK

        self.board[3][3] = Board_class.WHITE
        self.board[4][4] = Board_class.WHITE
        self.board[3][4] = Board_class.BLACK
        self.board[4][3] = Board_class.BLACK

        '''
        # Pre-assigned test pattern
        self.board[2][5] = Board_class.BLACK
        self.board[3][4] = Board_class.BLACK
        self.board[3][5] = Board_class.BLACK
        self.board[4][4] = Board_class.BLACK
        self.board[4][5] = Board_class.BLACK
        self.board[5][3] = Board_class.BLACK

        self.board[1][5] = Board_class.WHITE
        self.board[2][2] = Board_class.WHITE
        self.board[2][3] = Board_class.WHITE
        self.board[2][4] = Board_class.WHITE
        self.board[3][2] = Board_class.WHITE
        self.board[3][3] = Board_class.WHITE
        self.board[4][2] = Board_class.WHITE
        self.board[4][3] = Board_class.WHITE
        '''

    '''
    # Dump the board matrix to console (for debugging)
    '''
    def dump(self):
        print(" |0|1|2|3|4|5|6|7|")
        for y in list(range(8)):
            print(str(y)+"|", end = "")
            for x in list(range(8)):
                print("_" if self.board[y][x] == Board_class.BLANK else self.board[y][x], end = "|")
            print("")
        print("W,B=", str(self.scores()) + "\n===================")

    '''
    # Set board matrix having 'board' instance into 'myself' matrix
    '''
    def set(self, board):
        for y in list(range(8)):
            for x in list(range(8)):
                self.board[y][x] = board.board[y][x]
        return self

    '''
    # Copy 'myself' matrix and return new instance
    '''
    def copy(self, name):
        new = Board_class(name)
        new.restart()
        for y in list(range(8)):
            new.board[y] = self.board[y].copy()
        return new

    '''
    # Set a board instance name and return the name
    '''
    def name(self, nm=None):
        if not nm is None:
            self.board_name = nm
        return self.board_name
    
    '''
    # Get the reverse color
    '''
    def reverse_color(self,col):
        return Board_class.WHITE if col == Board_class.BLACK else Board_class.BLACK

    '''
    # Get number of each piece, return a tuple (whites, blacks)
    '''
    def scores(self):
        nw = 0
        nb = 0
        for y in list(range(8)):
            for x in list(range(8)):
                placed = self.board[y][x]
                if placed == Board_class.WHITE:
                    nw += 1
                elif placed == Board_class.BLACK:
                    nb += 1
        
        # (white-score, black-score)
        return(nw, nb)

    '''
    # Get tought mode at the moment in auto mode
    '''
    def get_auto_mode(self, turn_color):
        sc = self.scores()
        rt = (sc[0] if turn_color == Board_class.WHITE else sc[1]) / (sc[0] + sc[1])
        
        # Having much cells
        if rt >= 0.8:
            return Board_class.EVAL_MODE_pieces

        # balance or predominane
        if rt >= 0.6:
            return Board_class.EVAL_MODE_few_candidates

        # balance or predominane
        if rt >= 0.2:
            return Board_class.EVAL_MODE_many_places

        # Having few cells
        return Board_class.EVAL_MODE_pieces

    '''
    # Cell (x,y) is 'critical' cell for place_color turn.
    # 'place_color' is piece color placing at (x,y)
    # The significant function for game strategy,
    # PLEASE CUSTOMIZE HERE!!
    '''
    def is_critical_cell(self, x, y, place_color):
        global othello
        
        # Oppornent color
        opn = self.reverse_color(place_color)

        # No place for oppornent
        cands = self.candidates(opn)
        if len(cands) == 0:
            return 100000

        # DO NOT check critical case if 2 corners have been occupied
        '''
        global othello
        c = 0
        for cx in [0,7]:
            for cy in [0,7]:
                c += 0 if othello.board[cy][cx] == Board_class.BLANK else 1
                if c >= 2:
                    return 0
        '''

        # Check critical case
        posi = 0
        nega = 0
            
        # Symmetry1 (square corners)
        xy_flip = False
        if x == y or x + y == 7:
            if x >= 4:
                px = 7 - x
                mx = -1
            else:
                px = x
                mx = 1

            if y >= 4:
                py = 7 - y
                my = -1
            else:
                py = y
                my = 1

        # Symmetry2 (other cells)
        else:
            # x axis
            if y % 7 == 0:
                py = 0
                my = -1 if y>=4 else 1
                if x >= 4:
                    px = 7 - x
                    mx = -1
                else:
                    px = x
                    mx = 1

            # y axis
            elif x % 7 == 0:
                xy_flip = True
                py = 0
                mx = -1 if x>=4 else 1
                if y >= 4:
                    px = 7 - y
                    my = -1
                else:
                    px = y
                    my = 1
            else:
                px = x
                py = y
                mx = 1
                my = 1

        # Patern match
        place = (px, py)
#        print("PLACE:", (x,y), place, xy_flip, mx, my)
        if place in Board_class.critical_case:
            # Pattern definitions (=case)
            for case in Board_class.critical_case[place]:
                # xy_flip
                if xy_flip:
                    sx = case[1]
                    dx = case[3] * mx
                    if mx == -1:
                        sx = 7 - sx

                    sy = case[0]
                    dy = case[2] * my
                    if my == -1:
                        sy = 7 - sy

                # NOT xy-flip
                else:
                    sx = case[0]
                    dx = case[2] * mx
                    if mx == -1:
                        sx = 7 - sx

                    sy = case[1]
                    dy = case[3] * my
                    if my == -1:
                        sy = 7 - sy

                # Getting a pices line
                pieces = ""
                for i in list(range(case[4])):
                    p = self.board[sy][sx]
                    if p == place_color:
                        pieces += "W"
                    elif p == Board_class.BLANK:
                        pieces += "_"
                    else:
                        pieces += "B"
                        
                    # Next cell
                    sx += dx
                    sy += dy

                # Pattern match with regular expressions
                ptns = case[5]
                for ptn in ptns:

                    if not re.match(ptn[0], pieces) is None:
#                        print("===CRITICAL MATCH:", x, y, place, pieces, ptn)
                        if ptn[1] > 0:
                            posi += ptn[1]
                        else:
                            nega += ptn[1]

        # Give a corner or edge to oppornent
        for cand in cands:
            if cand[0] % 7 == 0:
                if cand[1] % 7 == 0:
                    nega -= 999999
                else:
                    nega -= ((int(abs(cand[1] - 3.5)) + 1) * 1000)
            elif cand[1] % 7 == 0:
                    nega -= ((int(abs(cand[0] - 3.5)) + 1) * 1000)

        # Get a corner in safe
#        if nega >= 0 and x % 7 == 0 and y % 7 == 0:
        if nega > -999999 and x % 7 == 0 and y % 7 == 0:
            return 1000000 + posi

        # Defence takes precedence over offence except top priority offence
        if posi < 1000000 and nega < 0:
            return nega
        
        return posi
    
    '''
    # return 1 if a  > b
    # return 2 if a  < b
    # return 0 if a == b
    '''
    def get_sign(self, a, b):
        return 1 if a > b else 2 if a < b else 0

    '''
    # Compare board1 and board2,
    #   idx: 0=white, 1=black
    #   return 1 if board1 is better than board2,
    #   return 2 if board2 is better than board1,
    #   return random (1 or 2) if board1 equals board2.
    # {"scores": , "mycands": , "opcands": , "evaluations": , "critical": , "checkmate": , "turns": , "board": }
    #   scores is a tuple (white pieces, black pieces).
    #   evaluations is a tuple (white evaluation, black evaluation).
    #   mycands is number of places I can place in this turn.
    #   opcands is number of places the oppornent can place in next turn.
    #   critical: True if positive critical situation for turn color.
    #   checkmate: True if any color gets the end of game without any piece on the board (score == 0)
    #   turns: number of turns getting to this situation.
    #   board: next turn's board (Board_class instance)
    '''
    def compare(self, board1, board2, idx):
        # Checkmate is the best
        if board1["checkmate"]:
            if board2["checkmate"]:
                return 1 if board1["turns"] <= board2["turns"] else 2
            else:
                return 1
        elif board2["checkmate"]:
            return 2

        sign_eval = self.get_sign(board1["evaluations"][idx], board2["evaluations"][idx])
        sign_scores = self.get_sign(board1["scores"][idx], board2["scores"][idx])
        sign_turns = self.get_sign(board2["turns"], board1["turns"])
        sign_mycands = self.get_sign(board1["mycands"], board2["mycands"])

        # Positive Critical case
        if board1["critical"] and board1["evaluations"][idx] > 0:
            if board2["critical"] and board2["evaluations"][idx] > 0:
                # Small number of turn is better
                if sign_turns!= 0:
                    return sign_turns

                # Large evaluations value is better
                if sign_eval != 0:
                    return sign_eval
                
                # Large number of score is better
                if sign_scores != 0:
                    return sign_scores
                
            else:
                return 1

        elif board2["critical"] and board2["evaluations"][idx] > 0:
            return 2
        
        # Negative Critical case
        if board1["evaluations"][idx] < 0:
            if board2["evaluations"][idx] < 0:
                return sign_eval
            else:
                return 2

        if board2["evaluations"][idx] < 0:
            return 1

        # Pieces
        if Board_class.eval_mode == Board_class.EVAL_MODE_pieces:
            # Large scores value if better
            if sign_scores != 0:
                return sign_scores
            
            # Many my candidates is better
            if sign_mycands != 0:
                return sign_mycands
                
        # Pieces (inverse)
        elif Board_class.eval_mode == Board_class.EVAL_MODE_pieces_inverse:
            # Little scores value if better
            if sign_scores != 0:
                return (sign_scores % 2) + 1
            
            # Many my candidates is better
            if sign_mycands != 0:
                return sign_mycands
                
        # Many cells to place
        elif Board_class.eval_mode == Board_class.EVAL_MODE_many_places:
            # Many my candidates is better
            if sign_mycands != 0:
                return sign_mycands

        # Little candidates (for opponent) value if better
        if board1["opcands"] < board2["opcands"]:
            return 1
    
        if board1["opcands"] > board2["opcands"]:
            return 2
            
        # Many my candidates is better
        if sign_mycands != 0:
            return sign_mycands

        # Large scores value if better
        if sign_scores != 0:
            return sign_scores
        
        # Large evaluations value is better
        if sign_eval != 0:
            return sign_eval
        
        # Small number of turn is better
        if sign_turns!= 0:
            return sign_turns

        # Make random strategy
        ut = int(time.time() + board1["scores"][idx] + board2["scores"][idx])
        rnd = ut % 2 + 1
        return rnd
    
    '''
    # Try placing a 'pc' color piece at (px,py) and reverse the opponent piece.
    # (dx,dy) is a direction reversing, (-1,1) = (to left, to bottom of board)
    # Return number of opponent pieces reversed, zero means 'NOT REVERSED AT ALL'
    # If 'reverse' == True, change the board matrix. False, not changed.
    '''
    def do_place(self, px, py, pc, dx, dy, reverse=False):
        # Counter color
        cc = self.reverse_color(pc)

        # Move to next cell
        judge = False
        cx = px + dx
        cy = py + dy
        rv = 0
        while cx >= 0 and cx <= 7 and cy >= 0 and cy <= 7:
            '''
            # Out of board
            if cx < 0 or cx > 7 or cy < 0 or cy > 7:
                break
            '''

            placed = self.board[cy][cx]
            # Find a blank cell
            if placed == Board_class.BLANK:
                break
            
            # Find my color
            elif placed == pc:
                # Reversed opponent piece(s) or not
                judge = True if rv > 0 else False
                break
            
            # Find opponent piece
            else:
                rv += 1    # sum of number of reversed pieces
                cx += dx
                cy += dy
        
        # Change board matrix
        if judge and reverse:
            cx = px
            cy = py
            self.board[py][px] = pc
            for r in list(range(rv)):
                cx += dx
                cy += dy
                self.board[cy][cx] = pc
            
        # Return number of reversed cells
        return rv if judge else 0

    '''
    # Place 'pc' color piece at (px,py) and return sum of number of reversed opponent pieces.
    # If 'reverse' == True, change the board matrix. False, not changed.
    '''
    def place_at(self, px, py, pc, reverse=False, possibility=False):
        if self.board[py][px] != Board_class.BLANK:
            return 0

        rev_total = 0
        for move in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
            rv = self.do_place(px, py, pc, move[0], move[1], reverse)
            if rv > 0:
                if possibility:
                    return rv
                rev_total += rv

        return rev_total
    
    '''    
    # Get candidates list of cells to be able to place 'pc' color piece.
    # List of tuple (x, y, numer of opponent cells reversed)
    '''
    def candidates(self, pc):
        cands = []
        for py in list(range(8)):
            for px in list(range(8)):
                if self.board[py][px] == Board_class.BLANK:
                    rv = self.place_at(px, py, pc, False, True)
                    if rv > 0:
                        cands.append((px, py, rv))

        return cands

    '''
    # Game over or not?
    # Game over if there is nowhere to place any place .
    '''
    def is_game_over(self):
        return len(self.candidates(Board_class.WHITE)) + len(self.candidates(Board_class.BLACK)) == 0

    '''
    # Trace a game tree by recursion call (depth first)
    # Return a 'best' board information in the possibles.
    #   selected_turn: {"scores": (w,b), "evaluations": (w,b), "checkmate": boolean, "turns": turns to the board, "board": board instance}
    # 'turn_color' is the current game turn's piece color.
    # 'place_color' is the 'my turn' color in simulation board.
    # 'current_level' is thought depth.
    # 'max_score' is the best board in possibles until now.
    '''
    def deep_turn(self, turn_color, place_color, current_level, max_score, background):
#        print(">>> deep_turn: BG=", background , " / place=", place_color, " / depth=", current_level)
        myturn = turn_color == place_color

        # Get candidates list to place a piece
        cands = self.candidates(place_color)
        cands_len = len(cands)

        # Get scores and evaluation values of this board
        sc = self.scores()

        # There is nowhere to place it
        if cands_len == 0:
            # Lose
            if myturn:
                return None
            # Win
            else:
                return {"scores": sc, "opcands": 0, "evaluations": sc, "critical": False, "checkmate": True, "turns": current_level, "board": None}

        #  Candidates list reduction
        elif cands_len > Board_class.LIMIT_CANDIDATES:
            cands = cands[0:Board_class.LIMIT_CANDIDATES]
            cands_len = len(cands)

        # Copy and make new board for simulation
        turn = self.copy("candidate")

        # Trace game trees for each candidate piece to place
        cands_deep = []
        cand_max = None
        for cand in cands:
            # Board starting next simulation
            turn.set(self)
            cand_score = None
            
            # Place one of candidate piece on the simulation board
            if turn.place_at(cand[0], cand[1], place_color, reverse=True) > 0:
                # Oppornent candidates
                cl = len(turn.candidates(self.reverse_color(place_color)))

                # Board scores
                sc = turn.scores()
                    
                # Checkmate (Black win)
                if sc[0] == 0:
                    # Placing bad, cut this path
                    if turn_color == Board_class.WHITE:
#                        print("---CHECKMATED PATH W+++")
                        return None
                    # Placing best
                    else:
#                        print("---CHECKMATE PATH B+++")
                        cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": sc, "critical": False, "checkmate": True, "turns": current_level, "board": None}

                # Checkmate (White win)
                elif sc[1] == 0:
                    # Placing bad, cut this path
                    if turn_color == Board_class.BLACK:
#                        print("+++CHECKMATED PATH B+++")
                        return None
                    # Placing best
                    else:
#                        print("+++CHECKMATE PATH W+++")
                        cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": sc, "critical": False, "checkmate": True, "turns": current_level, "board": None}

                # No candidate to place
                elif cl == 0:
#                    print("***NO PLACE D***")
#                    cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": (100000, -100000) if place_color == Board_class.WHITE else (-100000, 100000), "critical": True, "checkmate": False, "turns": current_level, "board": None}
                    # Turn color is making checkmate (win)
                    if turn_color == place_color:
                        cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": (100000, -100000) if place_color == Board_class.WHITE else (-100000, 100000), "critical": True, "checkmate": False, "turns": current_level, "board": None}
                    # Oppornent color is making checkmate (lose)
                    else:
                        cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": (-100000, 100000) if place_color == Board_class.WHITE else (100000, -100000), "critical": True, "checkmate": False, "turns": current_level, "board": None}

                # Think more deeply
                else:
                    # Is critical for place_color turn
                    think_deep = True
                    critical = turn.is_critical_cell(cand[0], cand[1], place_color)
                    
                    # Placing bad position, cut this path
                    if critical < 0:
#                        print("+++BAD PATH+++", critical)
                        # Turn player never choses this place
#                        if myturn and critical <= -99999:
#                            continue
                        think_deep = not myturn
                        
                        # Low risk for my turn, or oppornent has to accept this choses 
                        cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": (critical, -critical) if place_color == Board_class.WHITE else (-critical, critical), "critical": False, "checkmate": False, "turns": current_level, "board": None}

                    # Placing very good position
                    elif critical > 0:
                        think_deep = not myturn
#                        print("+++GOOD PATH+++:", think_deep, "=", critical)
                        cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": (critical, -critical) if place_color == Board_class.WHITE else (-critical, critical), "critical": True, "checkmate": False, "turns": current_level, "board": None}

                    # Place at an orinary cell
                    else:
                        cand_score = {"scores": sc, "mycands": cands_len, "opcands": cl, "evaluations": sc, "critical": False, "checkmate": False, "turns": current_level, "board": None}

                    # End of tree tracing (reached at maximum thought depth)
                    if myturn and current_level == Board_class.MAX_DEPTH:
                        think_deep = False

                    # Make deep think list
                    if think_deep:
                        if cand_max is None:
                            cand_max = cand_score
                            cands_deep.insert(0, (cand, cand_score))
                        # Sort descending
                        else:
                            ins = -1
                            for lst in cands_deep:
                                ins += 1
                                if self.compare(cand_score, lst[1], 0 if place_color == Board_class.WHITE else 1) == 1:
                                    cands_deep.insert(ins, (cand, cand_score))
                                    cand_score = None
                                    break

                            if not cand_score is None:
                                cands_deep.append((cand, cand_score))

                        cand_score = None

                # Compare the result of simulation board and the best board until now
                if not cand_score is None:
                    if max_score is None:
                        max_score = cand_score
                    else:
                        if self.compare(cand_score, max_score, 0 if place_color == Board_class.WHITE else 1) == 1:
                            max_score = cand_score

        # Think deeply
        for lst in cands_deep:
            cand = lst[0]
#            print("===DEEP THINK ", current_level, background, place_color, ":", cand)
            turn.set(self)
            turn.place_at(cand[0], cand[1], place_color, reverse=True)
            cand_score = turn.deep_turn(turn_color, self.reverse_color(place_color), current_level + (0 if myturn else 1), max_score, background)
            if not cand_score is None:
                if max_score is None:
                    max_score = cand_score
                # Try deep thought while candidate is top level critical
                else:
                    if self.compare(cand_score, max_score, 0 if place_color == Board_class.WHITE else 1) == 1:
                        max_score = cand_score
                    if (not cand_score["critical"]) or (cand_score["critical"] and cand_score["evaluations"][0 if place_color == Board_class.WHITE else 1] < 750000):
                        break

        # garbage collection
        del turn

        # Result
        return max_score

    '''
    # Register candidates of cell to place a piece in next turn,
    # and get one candidate by yield.  Both main core and multi-core get a candidate by 'next(generator)'.
    '''
    cands_list_yield = None
    cands_list_generator = None
    def candidates_list(self, cands_list):
        for cand in cands_list:
            yield cand

    '''
    # Trace a game tree by recursion call (depth first) for both multi-cores
    # Return a 'best' board information in the possibles.
    #   selected_turn: {"scores": (w,b), "evaluations": (w,b), "checkmate": boolean, "turns": turns to the board, "board": board instance}
    # 'turn_color' is the current game turn's piece color.
    # 'place_color' is the 'my turn' color in simulation board.
    # 'background' = True is for 2nd(sub) core, False is 1st(main) core.
    '''
    def evaluate_candidates(self, turn_color, background):
        global othello, cands_list_yield, cands_list_generator
        
        op_color = self.reverse_color(turn_color)

        # Tracing tree job
#        print("START JOB:", "BG" if background else "FG")
        
        # Multi-core process
        if background:
            Board_class.bg_selected_turn = None
            Board_class.bg_working = True
            Board_class.proc_cands_bg = 0
        else:
            Board_class.proc_cands = 0

        max_score = None
        while True:
            while not cands_list_yield is None:
                time.sleep(0.1)
                
            try:
                cands_list_yield = "M" if background else "C"
                cand = next(cands_list_generator)
#                print("===GET CANDIDATE:", cands_list_yield, "=", cand)
                cands_list_yield = None
                    
            except:
#                print("======END OF CANDIDATES LIST:", cands_list_yield)
                cands_list_yield = None
                break;

            # Clear evaluated boards list
            if background:
                Board_class.proc_cands_bg += 1
            else:
                Board_class.proc_cands += 1

#            gc.collect()

            print("*****EVAL CANDIDATE:", background, cand)
            turn = self.copy("candidate")
            cand_score = None

            # Place my turn
            if turn.place_at(cand[0], cand[1], turn_color, reverse=True) > 0:
                # Show CPU thought
                if background:
                    Board_class.evaluating_places[1] = (cand[0], cand[1])
                else:
                    Board_class.evaluating_places[0] = (cand[0], cand[1])
                    # Show the current CPU thought in main core (it seems to have something problems SPI/UART use in 2nd core)
                    display_othello(othello, turn_color)
                
                # Get status just after placing my piece
                sc = turn.scores()
                cl = len(turn.candidates(self.reverse_color(turn_color)))
#                cl = len(turn.candidates(self.turn_color)
#                print("CANDIDATE PLACED:", cand[0], cand[1], sc, cl)

                # Checkmate
                if sc[0] == 0:          # white is zero (lose)
                    if background:
                        Board_class.evaluating_places[1] = (-1, -1)
                    else:
                        Board_class.evaluating_places[0] = (-1, -1)

                    return {"cand": cand, "scores": sc, "mycands": Board_class.all_cands, "opcands": cl, "evaluations": (-99999, 99999) if turn_color == Board_class.WHITE else (99999, -99999), "critical": False, "checkmate": True, "turns": 0, "board": turn}

                elif sc[1] == 0:        # black is zero (lose)
                    if background:
                        Board_class.evaluating_places[1] = (-1, -1)
                    else:
                        Board_class.evaluating_places[0] = (-1, -1)

                    return {"cand": cand, "scores": sc, "mycands": Board_class.all_cands, "opcands": cl, "evaluations": (99999, -99999) if turn_color == Board_class.WHITE else (-99999, 99999), "critical": False, "checkmate": True, "turns": 0, "board": turn}

                elif cl == 0:
#                    print("***NO PLACE H***")
                    cand_score = {"scores": sc, "mycands": Board_class.all_cands, "opcands": cl, "evaluations": (100000, -100000) if turn_color == Board_class.WHITE else (-100000, 100000), "critical": True, "checkmate": False, "turns": 0, "board": None}

                # Take a critical cell (>0: very good for this turn, <0: very bad)
                else:
                    critical = turn.is_critical_cell(cand[0], cand[1], turn_color)
#                    print("CANDIDATE CRITICAL:", cand[0], cand[1], critical)
                    if critical != 0:
#                    if critical > 0:
                        print("***FIND CRITICAL PLACE:", cand[0], cand[1], critical)
                        # Place white piece at a critical cell
                        if turn_color == Board_class.WHITE:
                            cand_score =  {"scores": sc, "mycands": Board_class.all_cands, "opcands": cl, "evaluations": (critical, -critical), "critical": critical > 0, "checkmate": False, "turns": 0, "board": turn}
                        # Place black piece at a critical cell
                        else:
                            cand_score =  {"scores": sc, "mycands": Board_class.all_cands, "opcands": cl, "evaluations": (-critical, critical), "critical": critical > 0, "checkmate": False, "turns": 0, "board": turn}

                        if background:
                            Board_class.bg_selected_turn = cand_score
                            Board_class.evaluating_places[1] = (-1, -1)
                        else:
                            Board_class.evaluating_places[0] = (-1, -1)

                    # Ordinal cell
                    else:
                        # Depth first trace
                        cand_score = turn.deep_turn(turn_color, self.reverse_color(turn_color), 0, None, background)
                        if cand_score is None:
                            cand_score = {"scores": sc, "mycands": Board_class.all_cands, "opcands": cl, "evaluations": (-99999 if turn_color == Board_class.WHITE else 99999, 99999 if turn_color == Board_class.WHITE else -99999), "critical": False, "checkmate": False, "turns": 0, "board": turn}

                # Choose best cell
                if not cand_score is None:
                    if max_score is None:
                        max_score = cand_score
                        max_score["board"] = turn
                        max_score["cand"] = cand
                    else:
                        if self.compare(cand_score, max_score, 0 if turn_color == Board_class.WHITE else 1) == 1:
                            max_score = cand_score
                            max_score["board"] = turn
                            max_score["cand"] = cand

            if background:
                Board_class.evaluating_places[1] = (-1, -1)
            else:
                Board_class.evaluating_places[0] = (-1, -1)
                display_othello(othello, turn_color)
                

        # Store the background result in the instance variables
        if background:
            Board_class.evaluating_places[1] = (-1, -1)
            Board_class.bg_selected_turn = max_score
        else:
            Board_class.evaluating_places[0] = (-1, -1)
        
        # Result
#        print("***DECIDED CAND:", max_score, "BG=", background)
        return max_score


    '''
    # A resident program to think game strategy in mlti-core.
    # When Board_class.bg_cands has a candidates list,  this program runs.
    '''
    def evaluate_candidates_multi_core(self):
        global othello

        # Loop during be terminated (NOT SUPPORT CURRENTLY)
        while not Board_class.bg_terminate:
            # Wait for next job
            while not Board_class.bg_cands:
                time.sleep(0.1)

            # Done a job, go to waiting mode
            self.evaluate_candidates(Board_class.bg_turn_color, True)
            Board_class.bg_cands = False
            Board_class.bg_turn_color = Board_class.BLANK
            Board_class.bg_working = False

        Board_class.bg_wakeup = False


    '''
    # Start multi-core process (evaluate_candidates_multi_core)
    '''
    def start_multi_core(self):
        if not Board_class.bg_wakeup:
            try:
                Board_class.bg_wakeup = True
                res_thread = _thread.start_new_thread(self.evaluate_candidates_multi_core, ())
#                print("START MULTI-CORE.")
            except Exception as e:
                Board_class.bg_wakeup = False
                print("COULD NOT START MULTI-CORE:", e)
        
        return Board_class.bg_wakeup

    '''
    # Decied a next turn board from some candidates to place a piece
    # by tracing game tree in possibles and return the best result.
    # If there are some candidates to place a piece, use malti-core.
    # 'turn_color' is the color of the current turn (white or black)
    '''
    def next_turn(self, turn_color):
        global othello, cands_list_yield, cands_list_generator

        gc.collect()
        Board_class.proc_cands = 0
        Board_class.proc_cands_bg = 0

        # Get cells being able to place a piece
        cands = self.candidates(turn_color)
        cands_len = len(cands)
        print("CANDIDATES[", cands_len, "] = ", cands)

        # No cell to place it
        if cands_len == 0:
            # Lose
            return None
        
        # Only one candidate
        elif cands_len == 1:
            # Copy and make new board and place a piece at a candidate cell
            turn = self.copy("candidate")
            turn.place_at(cands[0][0], cands[0][1], turn_color, reverse=True)
            score = turn.scores()
            return {"cand": (cands[0][0], cands[0][1], 0), "scores": score, "mycands": 1, "opcands": len(turn.candidates(self.reverse_color(turn_color))), "evaluations": score, "critical": False, "checkmate": False, "turns": 1, "board": turn}            

        # Candidates list reduction
        else:
            # Limit to maximum candidates number to decrese possibilities (= calculation time)
            # Remove lower evaluation value.
            if cands_len >= Board_class.LIMIT_CANDIDATES:
                cands = cands[0:Board_class.LIMIT_CANDIDATES]
                cands_len = len(cands)
#                print("LIMITED:", cands)
        
        # Candidates list
        Board_class.all_cands = len(cands)
        cands_list_generator = self.candidates_list(cands)
        cands_list_yield = None

        # Clear multi-core result
        Board_class.bg_selected_turn = None
        gc.collect()
#        print("GC FREE MEMORY=", gc.mem_free())

        # Evaluate candidates with multi core
        if self.start_multi_core():
            Board_class.bg_working = True
            Board_class.bg_turn_color = turn_color
            Board_class.bg_cands = True
        else:
            Board_class.bg_working = False
            Board_class.bg_turn_color = Board_class.BLANK
            Board_class.bg_cands = False
#            print("MULTI-CORE DOSE NOT WORK.")

        # Evaluate candidates with main core
        selected_turn = self.evaluate_candidates(turn_color, False)
        
        # Wait for end of multi-core job
        while Board_class.bg_working:
            # Show 2nd CPU thought
            display_othello(othello, turn_color)
            time.sleep(1)
                
        Board_class.all_cands = 0
        Board_class.proc_cands = 0
        Board_class.proc_cands_bg = 0
        print("=======JOIN MULTI-CORES.=======")
        print("CORE0:", selected_turn)
        print("CORE1:", Board_class.bg_selected_turn)
        
        # Compare the results of main-core and multi-core
        if not selected_turn is None:
            if not Board_class.bg_selected_turn is None:
                if self.compare(selected_turn, Board_class.bg_selected_turn, 0 if turn_color == Board_class.WHITE else 1) == 2:
                    del selected_turn["board"]
                    selected_turn = Board_class.bg_selected_turn
                    selected_turn["board"] = Board_class.bg_selected_turn["board"]
                    
        elif not Board_class.bg_selected_turn is None:
            selected_turn = Board_class.bg_selected_turn
            selected_turn["board"] = Board_class.bg_selected_turn["board"]
        
        # garbage collection
        gc.collect()

        # Return the best result
        print("===DECIDED BOARD:", selected_turn)
        return selected_turn

'''
# Show garphic text class
'''
class Graphic_Text:
    '''
    # Initialization
    # 'lcd' is a LCD class instance.
    '''
    def __init__(self, lcd):
        self.LCD = lcd
        self.font = {}                   # 9x9 Bitmap font definitions
        self.font["0"] = [0b001111100,
                          0b010000010,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b010000010,
                          0b001111100]
        
        self.font["1"] = [0b000010000,
                          0b000110000,
                          0b000010000,
                          0b000010000,
                          0b000010000,
                          0b000010000,
                          0b000010000,
                          0b000010000,
                          0b001111100]
        
        self.font["2"] = [0b011111110,
                          0b100000001,
                          0b000000001,
                          0b000000001,
                          0b011111111,
                          0b100000000,
                          0b100000000,
                          0b100000000,
                          0b111111111]
        
        self.font["3"] = [0b011111110,
                          0b100000001,
                          0b000000001,
                          0b000000001,
                          0b000111110,
                          0b000000001,
                          0b000000001,
                          0b100000001,
                          0b011111110]
        
        self.font["4"] = [0b000001100,
                          0b000010100,
                          0b000100100,
                          0b001000100,
                          0b010000100,
                          0b111111111,
                          0b000000100,
                          0b000000100,
                          0b000001110]
        
        self.font["5"] = [0b111111111,
                          0b100000000,
                          0b100000000,
                          0b100000000,
                          0b11111111,
                          0b000000001,
                          0b000000001,
                          0b100000001,
                          0b111111110]
        
        self.font["6"] = [0b011111110,
                          0b100000001,
                          0b100000000,
                          0b100000000,
                          0b111111110,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b011111110]
        
        self.font["7"] = [0b111111111,
                          0b100000001,
                          0b000000010,
                          0b000000100,
                          0b000001000,
                          0b000010000,
                          0b000010000,
                          0b000010000,
                          0b000010000]
        
        self.font["8"] = [0b011111110,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b011111110,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b011111110]
        
        self.font["9"] = [0b011111110,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b011111111,
                          0b000000001,
                          0b000000001,
                          0b100000010,
                          0b011111100]
        
        self.font["R"] = [0b111111100,
                          0b100000010,
                          0b100000001,
                          0b100000010,
                          0b111111100,
                          0b100001000,
                          0b100000100,
                          0b100000010,
                          0b100000001]
        
        self.font["S"] = [0b011111110,
                          0b100000001,
                          0b100000000,
                          0b010000000,
                          0b001111100,
                          0b000000010,
                          0b100000001,
                          0b100000001,
                          0b011111110]
        
        self.font["W"] = [0b110000011,
                          0b100000001,
                          0b100000001,
                          0b100010001,
                          0b100010001,
                          0b100010001,
                          0b100010001,
                          0b010101010,
                          0b001000100]
        
        self.font["L"] = [0b100000000,
                          0b100000000,
                          0b100000000,
                          0b100000000,
                          0b100000000,
                          0b100000000,
                          0b100000001,
                          0b100000011,
                          0b111111111]
        
        self.font["D"] = [0b111111100,
                          0b100000010,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000010,
                          0b111111100]
        
        self.font["P"] = [0b111111100,
                          0b100000010,
                          0b100000001,
                          0b100000010,
                          0b111111100,
                          0b100000000,
                          0b100000000,
                          0b100000000,
                          0b100000000]
        
        self.font["*"] = [0b000010000,
                          0b010010010,
                          0b001010100,
                          0b000111000,
                          0b111111111,
                          0b000111000,
                          0b001010100,
                          0b010010010,
                          0b000010000]
        
        self.font["C"] = [0b001111100,
                          0b010000010,
                          0b100000001,
                          0b100000000,
                          0b100000000,
                          0b100000000,
                          0b100000001,
                          0b010000010,
                          0b001111100]
        
        self.font["M"] = [0b110000011,
                          0b101000101,
                          0b100101001,
                          0b100010001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b110000011]
        
        self.font["U"] = [0b110000011,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b100000001,
                          0b010000010,
                          0b001111100]

    '''
    # Show graphical ascii character on LCD
    '''
    def show_graphic_ascii(self, ch, x, y, w, h, forecolor, backcolor):
        if ch in self.font:
            dots = self.font[ch]
            ry = y
            for row in dots:
                rx = x
                for bit in [0b100000000, 0b010000000, 0b001000000, 0b000100000, 0b000010000, 0b000001000, 0b000000100, 0b000000010,0b000000001]:
                    self.LCD.fill_rect(rx, ry, w, h, backcolor if (row & bit) == 0 else forecolor)
                    rx += w
                    
                ry += h            
    
    '''
    # Show graphical text string on LCD
    '''
    def show_graphic_text(self, str, x, y, w, h, sp, forecolor, backcolor):
        for ch in str:
            self.show_graphic_ascii(ch, x, y, w, h, forecolor, backcolor)
            x = x + w * 9 + sp


'''
# Display 'othello' instance board on LCD.
'''
in_display_othello = False
def display_othello(othello, next_turn, placed_cell = None):
    global LCD, GT, in_display_othello
    
    if in_display_othello:
        return

    in_display_othello = True
    while LCD.cs() == 0 or LCD.tp_cs() == 0:
        time.sleep(0.1)
    
    cell_size = 40
    cell_half = 20
    
    # Draw board
    game_over = othello.is_game_over()
    score = othello.scores()
    candw = othello.candidates(Board_class.WHITE)
    candb = othello.candidates(Board_class.BLACK)
    for row in list(range(4)):
        LCD.fill(LCD.BLACK)
        LCD.fill_rect(0, 0, 80, 80, LCD.BROWN)
        LCD.fill_rect(400, 0, 80, 80, LCD.BROWN)
        
        vs  = 2 if Board_class.white_is_cpu else 0
        vs += 1 if Board_class.black_is_cpu else 0

        # White turn
        if row == 0:
            col = LCD.WHITE if Board_class.white_is_cpu else LCD.YELLOW
            if Board_class.white_is_cpu:
                GT.show_graphic_text(str(Board_class.LIMIT_CANDIDATES), 4, 35, 1, 1, 0, col, LCD.BROWN)
                GT.show_graphic_text("C", 26, 20, 3, 3, 0, col, LCD.BROWN)
                GT.show_graphic_text(str(Board_class.eval_mode), 57, 23, 1, 1, 0, LCD.SKYBLUE if Board_class.auto_mode else col, LCD.BROWN)
                GT.show_graphic_text(str(Board_class.MAX_DEPTH), 57, 36, 1, 1, 0, col, LCD.BROWN)
            else:
                GT.show_graphic_text("M", 26, 20, 3, 3, 0, col, LCD.BROWN)
            
            GT.show_graphic_text("MC", 410,  3, 3, 3, 5, LCD.YELLOW if vs == 1 else LCD.ORANGE, LCD.BROWN)
            GT.show_graphic_text("CM", 410, 43, 3, 3, 5, LCD.YELLOW if vs == 2 else LCD.ORANGE, LCD.BROWN)
            
            if game_over:
                GT.show_graphic_text("W" if score[0] > score[1] else "L" if score[0] < score[1] else "D", 26, 50, 3, 3, 0, col, LCD.BROWN)
            elif next_turn == Board_class.WHITE:
                GT.show_graphic_text("P" if len(candw) == 0 else "*", 26, 50, 3, 3, 0, col, LCD.BROWN)
                    
        # White score
        elif row == 1:
            sc = str(score[0])
            if len(sc) == 1:
                sc = " " + sc

            GT.show_graphic_text(sc, 10, 10, 3, 6, 2, LCD.WHITE, LCD.BROWN)
            
            GT.show_graphic_text("CC", 410,  3, 3, 3, 5, LCD.YELLOW if vs == 3 else LCD.ORANGE, LCD.BROWN)
            GT.show_graphic_text("MM", 410, 43, 3, 3, 5, LCD.YELLOW if vs == 0 else LCD.ORANGE, LCD.BROWN)
        
        # Black score
        elif row == 2:
            sc = str(score[1])
            if len(sc) == 1:
                sc = " " + sc
            
            GT.show_graphic_text(sc, 10, 20, 3, 6, 2, LCD.BLACK, LCD.BROWN)
            GT.show_graphic_text("UD" if Board_class.in_play else "PL", 410, 43, 3, 3, 5, LCD.PINK, LCD.BROWN)

            if Board_class.in_play and Board_class.all_cands > 0:
                GT.show_graphic_text(str(Board_class.all_cands) + "S" + str(Board_class.proc_cands) + "M" + str(Board_class.proc_cands_bg), 405, 13, 1, 1, 3, LCD.MINT, LCD.BROWN)

        # Black turn
        elif row == 3:
            col = LCD.BLACK if Board_class.black_is_cpu else LCD.YELLOW
            if Board_class.black_is_cpu:
                GT.show_graphic_text(str(Board_class.LIMIT_CANDIDATES), 4, 50, 1, 1, 0, col, LCD.BROWN)
                GT.show_graphic_text("C", 26, 35, 3, 3, 0, col, LCD.BROWN)
                GT.show_graphic_text(str(Board_class.eval_mode), 57, 38, 1, 1, 0, LCD.SKYBLUE if Board_class.auto_mode else col, LCD.BROWN)
                GT.show_graphic_text(str(Board_class.MAX_DEPTH), 57, 51, 1, 1, 0, col, LCD.BROWN)
            else:
                GT.show_graphic_text("M", 26, 35, 3, 3, 0, col, LCD.BROWN)

            GT.show_graphic_text("RS", 410, 43, 3, 3, 5, LCD.PINK if Board_class.in_play else LCD.BLACK, LCD.BROWN)

            if game_over:
                GT.show_graphic_text("W" if score[0] < score[1] else "L" if score[0] > score[1] else "D", 26, 3, 3, 3, 0, col, LCD.BROWN)
            elif next_turn == Board_class.BLACK:
                GT.show_graphic_text("P" if len(candb) == 0 else "*", 26, 3, 3, 3, 0, col, LCD.BROWN)
            
        # Cells
        y = 0
        for dy in list(range(2)):
            x = 80
            for dx in list(range(8)):
                if Board_class.touched_cell is None:
                    LCD.fill_rect(x, y, cell_size, cell_size, LCD.GREEN)
                else:
                    LCD.fill_rect(x, y, cell_size, cell_size, LCD.SKYBLUE if Board_class.touched_cell == (dx, row*2+dy) else LCD.GREEN)                    

                c = othello.board[row*2+dy][dx]
                if c != Board_class.BLANK:
                    LCD.ellipse(x + cell_half, y + cell_half, cell_half - 4, cell_half - 4, LCD.WHITE if c == Board_class.WHITE else LCD.BLACK, True)

                LCD.rect(x, y, cell_size, cell_size, LCD.BROWN)
                LCD.rect(x+1, y+1, cell_size-2, cell_size-2, LCD.BROWN)
                x += cell_size

            y += cell_size

        # Evaluationg cell by main-core if exists
        for c in [0,1]:
            if Board_class.evaluating_places[c][0] != -1:
                ex = Board_class.evaluating_places[c][0]
                ey = Board_class.evaluating_places[c][1]
                if row*2 <= ey and ey <= row*2+1:
                    ey = ey % 2
                    LCD.ellipse(ex * cell_size + cell_half + 80, ey * cell_size + cell_half, cell_half - 4, cell_half - 4, LCD.RED if c == 0 else LCD.MAGENTA, True)

        # Placed cell by CPU just before
        if not placed_cell is None:
            ex = placed_cell[0]
            ey = placed_cell[1]
            if row*2 <= ey and ey <= row*2+1:
                ey = ey % 2
                x = ex * cell_size + 80
                y = ey * cell_size
                LCD.rect(x, y, cell_size, cell_size, LCD.SKYBLUE)
                LCD.rect(x+1, y+1, cell_size-2, cell_size-2, LCD.SKYBLUE)

        # Show a row of LCD
        LCD.show(row * 80, row * 80 + 79)
        
    time.sleep(0.5)
    in_display_othello = False


'''
# Callback function called by IRQ by PIO periodically.
# Get a touch coordinates and store the global variables (LCD_touch_x, LCD_touch_y),
# or None if not touched.
'''
in_timer_func = False
def timer_func(x):
    global LCD, LCD_touch_x, LCD_touch_y, in_timer_func, in_display_othello

    if in_timer_func or in_display_othello:
        return

    LCD_touch_x = None
    LCD_touch_y = None

    if LCD.cs() == 0 or LCD.tp_cs() == 0:
        return

    in_timer_func = True
    get = LCD.touchpanel_get(TouchLCD_3inch5.GET_TOUCH, None, None, None)
    if not get is None:
        (LCD_touch_x, LCD_touch_y) = LCD.touch_pixel_get(get)
#        print("TIMER TOUCH:", LCD_touch_x, LCD_touch_y)

    in_timer_func = False


# Touch
def touch_action(othello, x, y, player):
    # On othello board
    if 80 <= x and x <= 399:
        cx = int((x - 80) / 40)
        cy = int(y/40)
        if 0 <= cx and cx <= 7 and 0 <= cy and cy <= 7:
            if othello.place_at(cx, cy, player, False, True) > 0:
                return (cx, cy)

    elif x >= 440:
        # Reset button
        if y >= 280:
            return(-1, -1)

        # Undo button
        elif y >= 200:
            return(-2, -2)

    return None

'''
# GUI for uman player's turn.
# Wait for a touch LCD and get the coordinates.
#  
#  UD: Undo (back to the previous human turn's board = 'undo_board')
#  RS: Restart game.
'''
def man_turn(othello, undo_board, player):
    global LCD, LCD_touch_x, LCD_touch_y, in_timer_func, in_display_othello
    
    # Check to pass or not
    cands = othello.candidates(player)
    
    # Must pass
    if len(cands) == 0:
        return 1
    
    while LCD.cs() == 0 or LCD.tp_cs() == 0:
        time.sleep(0.05)

    # Wait for touch screen
    Board_class.touched_cell = None
    res_touch = None
    ret = 2
    while True:
        LCD_touch_x = None
        LCD_touch_y = None
        X_Point = None
        Y_Point = None
        
        # Wait for a touch
        while X_Point is None or Y_Point is None:
            X_Point = LCD_touch_x
            Y_Point = LCD_touch_y
            time.sleep(0.05)
        
        # Do a touch action
        if not X_Point is None and not Y_Point is None:
            res_touch = touch_action(othello, X_Point, Y_Point, player)
            
            # Touch something
            if not res_touch is None:
                (x, y) = res_touch

                # Touch a cell which a piece can place there
                if 0 <= x and x <= 7 and 0 <= y and y <= 7:
                    
                    # First touch
                    if Board_class.touched_cell is None:
                        Board_class.touched_cell = (x, y)
                    # 2nd touch
                    elif Board_class.touched_cell == (x, y):
                        # Save board for undo
                        undo_board.set(othello)
                    
                        # Place a piece
                        othello.place_at(x, y, player, True)
                        ret = 0
                        break
                    # Clear first touch
                    else:
                        Board_class.touched_cell = (x, y)
                        
                    # redraw
                    while in_display_othello:
                        time.sleep(0.1)
                        
                    display_othello(othello, player)

                # Undo button
                elif x == -2 and y == -2:
                    if not undo_board is None:
                        undo_board.dump()
                        othello.set(undo_board)
                        time.sleep(0.1)
                        
                        # redraw
                        while in_display_othello:
                            time.sleep(0.1)
                            
                        display_othello(othello, player)

                # Reset button
                else:
                    ret = -1
                    break
        
        time.sleep(0.5)
    
    Board_class.touched_cell = None
    return ret


'''
# Select game mode.
#   MC: Human vs CPU, CM: CPU vs Human, CC: CPU vs CPU, MM:Human vs Human
#   PL: Start playing a game.
'''
def select_game_mode():
    global LCD, LCD_touch_x, LCD_touch_y, in_timer_func

    while LCD.cs() == 0 or LCD.tp_cs() == 0:
        time.sleep(0.1)

#    print("===SELECT GAME MODE then PLAY===")
    while True:
        LCD_touch_x = None
        LCD_touch_y = None
        X_Point = None
        Y_Point = None
        while X_Point is None or Y_Point is None:
            X_Point = LCD_touch_x
            Y_Point = LCD_touch_y
            time.sleep(0.1)
            
        if not X_Point is None and not Y_Point is None:
            if X_Point >= 400:
                if Y_Point <= 40:
                    Board_class.white_is_cpu = False
                    Board_class.black_is_cpu = True
                    return True
                elif Y_Point <= 80:    
                    Board_class.white_is_cpu = True
                    Board_class.black_is_cpu = False
                    return True
                elif Y_Point <= 120:    
                    Board_class.white_is_cpu = True
                    Board_class.black_is_cpu = True
                    return True
                elif Y_Point <= 160:    
                    Board_class.white_is_cpu = False
                    Board_class.black_is_cpu = False
                    return True
                elif Y_Point <= 240:
                    return False


'''
### MAIN ###
'''
if __name__=='__main__':
    # CPU clock 240MHz
#    machine.freq(133000000)
    machine.freq(240000000)

    # Initialize LCD and prepare for a frame buffer
    LCD = TouchLCD_3inch5(480, 80)
    
    # LCD backlight dark:0..100:bright
    LCD.bl_ctrl(40)    

    # Graphic text class
    GT = Graphic_Text(LCD)
    
    # CLOCK LED PIN definition GPIO1 (physical=2)
    pio0sm0 = rp2.StateMachine(0, pio_clock_irq, freq = 8000)
    rp2.PIO(0).irq(timer_func)
    LCD_touch_x = None
    LCD_touch_y = None

    # Othello game
    othello = Board_class("playing")
    othello.restart()
    display_othello(othello, Board_class.WHITE)

    # Undo object
    undo_board = Board_class("undo_board")
    undo_board.restart()

    # Game loop
    while True:
        # Initialize the board
        Board_class.in_play = False
        display_othello(othello, Board_class.WHITE)
        turn = 0
        pass_num = 0
        Board_class.auto_mode = False

        # Activate PIO during human GUI
        # StateMachine (PIO0SM0)
        pio0sm0.active(1)
        
        # Select game mode
        while select_game_mode():
            display_othello(othello, Board_class.WHITE)

        # Stop GUI IRQ
        pio0sm0.active(0)

        # Start a game
        Board_class.in_play = True
        othello.restart()
        undo_board.set(othello)
        display_othello(othello, Board_class.WHITE)
        othello.dump()

        # Random strategy
        Board_class.strategy = Board_class.strategies[int(time.time()) % len(Board_class.strategies)]

        # One game loop
        while pass_num < 2:
            if turn in Board_class.strategy:
#                print("@@@:", turn, Board_class.strategy[turn])
                Board_class.LIMIT_CANDIDATES = Board_class.strategy[turn][0]
                Board_class.MAX_DEPTH = Board_class.strategy[turn][1]
                if Board_class.strategy[turn][2] == Board_class.EVAL_MODE_auto:
                    Board_class.auto_mode = True
                else:
                    Board_class.auto_mode = False
                    Board_class.eval_mode = Board_class.strategy[turn][2]

            # White turn
            placed_cell = None
            turn += 1
            if Board_class.auto_mode and Board_class.white_is_cpu:
                Board_class.eval_mode = othello.get_auto_mode(Board_class.WHITE)

            # White CPU
            if Board_class.white_is_cpu:
                if Board_class.black_is_cpu:
                    time.sleep(1)
                    
                print("=====TURN WHITE CPU=====")
                max_score = othello.next_turn(Board_class.WHITE)
                if max_score is None:
                    pass_num += 1
                    print("=====PASS WHITE CPU=====")
                else:
                    print("=====TURN", turn, ": WHITE CPU=====")
                    pass_num = 0
                    placed_cell = max_score["cand"]
                    othello.set(max_score["board"])
                    del max_score["board"]

            # White human
            else:
                # Activate PIO during human turn only
                print("=====TOUCH for WHITE=====")
                pio0sm0.active(1)    # Start GUI IRQ
                res_man = man_turn(othello, undo_board, Board_class.WHITE)
                pio0sm0.active(0)    # Stop GUI IRQ
            
                # pass
                if res_man == 1:
                    pass_num += 1
                    print("=====PASS WHITE=====")
  
                # reversed
                elif res_man == 0:
                    pass_num = 0
                    
                # Reset button
                elif res_man == -1:
#                    print("===RESET===")
                    break

            # Redraw
            Board_class.evaluating_places[1] = (-1, -1)
            Board_class.evaluating_places[0] = (-1, -1)
            while in_display_othello:
                time.sleep(0.1)
            display_othello(othello, Board_class.BLACK, placed_cell)
            othello.dump()

            # Black turn
            placed_cell = None
            turn += 1
            if Board_class.auto_mode and Board_class.black_is_cpu:
                Board_class.eval_mode = othello.get_auto_mode(Board_class.BLACK)
        
            # Black CPU
            if Board_class.black_is_cpu:
                if Board_class.white_is_cpu:
                    time.sleep(1)
                    
                print("=====TURN BLACK CPU=====")
                max_score = othello.next_turn(Board_class.BLACK)
                if max_score is None:
                    pass_num += 1
                    print("=====PASS BLACK CPU=====")
                else:
                    print("=====TURN", turn, ": BLACK CPU=====")
                    pass_num = 0
                    placed_cell = max_score["cand"]
                    othello.set(max_score["board"])
                    del max_score["board"]
            
            # Black human
            else:
                # Activate PIO during human turn only
                print("=====TOUCH for BLACK=====")
                pio0sm0.active(1)    # Start GUI IRQ
                res_man = man_turn(othello, undo_board, Board_class.BLACK)
                pio0sm0.active(0)    # Stop GUI IRQ
            
                # pass
                if res_man == 1:
                    pass_num += 1
                    print("=====PASS WHITE=====")
            
                # reversed
                elif res_man == 0:
                    pass_num = 0
                    
                # Reset button
                elif res_man == -1:
                    print("===RESET===")
                    break

            # Redraw
            Board_class.evaluating_places[1] = (-1, -1)
            Board_class.evaluating_places[0] = (-1, -1)
            while in_display_othello:
                time.sleep(0.1)
            display_othello(othello, Board_class.WHITE, placed_cell)
            othello.dump()

        # Show scores
        score = othello.scores()
        print("GAME RESULT: WHITE=", score[0], "/ BLACK=", score[1])


