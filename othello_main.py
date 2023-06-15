'''
# Othello (Reversi) game program for Raspberry Pi PICO
# with Touch LCD display (WAVESHARE Pico-Res Touch-LCD-3.5inch)
#
# This program uses multi-core to think game strategy.
#
# Copyright Shunsuke Ohira, 2023
'''

import time, machine, _thread
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
    LIMIT_CANDIDATES = 6
    
    # Thought depth (actual depth = MAX_DEPTH * 2 - 1 (my turn + opponent turn))
    MAX_DEPTH = 2
    
    # EVAL_MODE: Evaluation mode to change evaluation value and algorithm in self.evaluations() etc.
    EVAL_MODE_pieces = 2
    EVAL_MODE_pieces_inverse = 3
    EVAL_MODE_eval = 4
    EVAL_MODE_eval_diff = 5
    eval_mode = EVAL_MODE_pieces_inverse
    
    # Evaluation values to put a piece at each cell, value should be lower 10000
    EVAL_PUT0 = [                         
            [99, 1, 5, 6, 6, 5, 1,99],
            [ 1, 0, 7, 7, 7, 7, 0, 1],
            [ 5, 7, 8, 8, 8, 8, 7, 5],
            [ 6, 7, 8, 9, 9, 8, 7, 6],
            [ 6, 7, 8, 9, 9, 8, 7, 6],
            [ 5, 7, 8, 8, 8, 8, 7, 5],
            [ 1, 0, 7, 7, 7, 7, 0, 1],
            [99, 1, 5, 6, 6, 7, 1,99]
        ]

    # Select a evaluation values maxtrix(EVAL_PUT*) to put a piece on the game board
    eval_place = None

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

    left_cands = 0
    left_cands_bg = 0

    # Already evaluated board names list used for cutting path evaluated in past.
    evaluated_list = []
    evaluated_list_bg = []
    
    # Candidate places evaluating currently (main-core and muti-core), used for only showing them on board
    evaluating_places = [(-1,-1),(-1,-1)]
    
    '''
    # Class instance initialization and instance variables
    '''
    def __init__(self, name):
        self.board_name = name         # Othello board instance name (usefully for debugging)
        self.board = [                 # Othello board matrix: " "=blank, "O"=white, "#"=black
                [" "," "," "," "," "," "," "," "],
                [" "," "," "," "," "," "," "," "],
                [" "," "," "," "," "," "," "," "],
                [" "," "," "," "," "," "," "," "],
                [" "," "," "," "," "," "," "," "],
                [" "," "," "," "," "," "," "," "],
                [" "," "," "," "," "," "," "," "],
                [" "," "," "," "," "," "," "," "]
            ]
    
    '''
    # Restart game
    '''
    def restart(self, white_list, black_list):
        for y in list(range(8)):
            for x in list(range(8)):
                self.board[y][x] = Board_class.BLANK

        for xy in white_list:
            self.board[xy[1]][xy[0]] = Board_class.WHITE
                
        for xy in black_list:
            self.board[xy[1]][xy[0]] = Board_class.BLACK

    '''
    # Dump the board matrix to console (for debugging)
    '''
    def dump(self):
        print("===BOARD:" + self.board_name + "===")
        print("  01234567")
        for y in list(range(8)):
            print(str(y)+":", end = "")
            for x in list(range(8)):
                print(self.board[y][x], end = "")
            print("")
        print("-----------------------------")
        print("Game Over=", self.is_game_over(), "/", self.scores(), "/", self.evaluations(), "depth=", Board_class.MAX_DEPTH)
        print("=============================")

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
        for y in list(range(8)):
            new.board[y] = self.board[y].copy()
        return new

    '''
    # Release the board matrix memory
    '''
    def release(self):
        self.board_name = None
        del self.board
#        gc.collect()

    '''
    # Release board matrix memory just after an instance is deleted
    '''
    def __del__(self):
        self.board_name = None
        del self.board
#        gc.collect()

    '''
    # Set a board instance name and return the name
    '''
    def name(self, nm=None):
        if not nm is None:
            self.board_name = nm
        return self.board_name

    '''
    # Generate this board name by board layout.
    '''
    def auto_name(self):
        # Board layout --> unique string
        name = ""
        nm = ""
        for y in list(range(8)):
            for x in list(range(8)):
                nm += self.board[y][x]
        
        # Shorten the name to decrease memory allocation
        prev = ""
        cnt = 0
        for ch in nm:
            if ch != prev:
                if prev != "":
                    name += prev
                    if cnt >= 2:
                        name = name + str(cnt)
                    
                prev = ch
                cnt = 1
            else:
                cnt += 1

        name += prev
        if cnt >= 2:
            name = name + str(cnt)
        
        # More shorten
        name = name.replace(" O", "W")
        name = name.replace(" #", "B")
        name = name.replace("O ", "X")
        name = name.replace("# ", "C")
        name = name.replace("O#", "Y")
        name = name.replace("#O", "D")

        return self.name(name)

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
    # Evaluate game board status for each color, used for choosing a next turn
    # The significant function for game strategy.
    # PLEASE CUSTOMIZE HERE!!
    '''
    def evaluations(self):
        sc = self.scores()
        tl = sc[0] + sc[1]
        return (sc[0] / tl, sc[1] / tl)

    '''
    # Cell (x,y) is 'critical' cell for game or not.
    # 'turn_color' is piece color of the current turn.
    # 'place_color' is piece color placing at (x,y)
    # The significant function for game strategy.
    # PLEASE CUSTOMIZE HERE!!
    '''
    def is_critical_cell(self, x, y, turn_color, place_color):
        # Coners are the critical cells
        if (x == 0 or x == 7) and (y == 0 or y == 7):
            return 59999 if turn_color == place_color else -59999
        
        # Oblique next to a corner cell
        col = self.board[y][x]
        if (x == 1 or x == 6) and (y == 1 or y == 6):
            cx = x + (-1 if x == 1 else 1)
            cy = y + (-1 if y == 1 else 1)
            x = x + (1 if x == 1 else -1)
            y = y + (1 if y == 1 else -1)
            if self.board[cy][cx] == Board_class.BLANK and self.board[y][x] != col:
                return -39999 if turn_color == place_color else 39999

            return -29999 if turn_color == place_color else 29999
        
        # Periphery
        if x == 0 or x == 7:
            if y == 1 or y == 6:
                if self.board[x][y + (-1 if y == 1 else 1)] == Board_class.BLANK and self.board[x][y + (1 if y == 1 else -1)] != col:
                    return -39999 if turn_color == place_color else 39999

            blank = 0
            white = 0
            black = 0
            prev = -1
            for cy in list(range(8)):
                col = self.board[cy][x]
                if col != prev:
                    if col == Board_class.BLANK:
                        blank += 1
                        prev = Board_class.BLANK
                    elif col == Board_class.WHITE:
                        white += 1
                        prev = Board_class.WHITE
                    else:
                        black += 1
                        prev = Board_class.BLACK
                        
            if white == 1 and black == 0:
                return 19999 if turn_color == Board_class.WHITE else -19999
            if black == 1 and white == 0:
                return 19999 if turn_color == Board_class.BLACK else -19999

        elif y == 0 or y == 7:
            if x == 1 or x == 6:
                if self.board[x + (-1 if x == 1 else 1)][y] == Board_class.BLANK and self.board[x + (1 if x == 1 else -1)][y] != col:
                    return -39999 if turn_color == place_color else 39999

            blank = 0
            white = 0
            black = 0
            prev = -1
            for cx in list(range(8)):
                col = self.board[y][cx]
                if col != prev:
                    if col == Board_class.BLANK:
                        blank += 1
                        prev = Board_class.BLANK
                    elif col == Board_class.WHITE:
                        white += 1
                        prev = Board_class.WHITE
                    else:
                        black += 1
                        prev = Board_class.BLACK
            
            if white == 1 and black == 0:
                return 19999 if turn_color == Board_class.WHITE else -19999
            if black == 1 and white == 0:
                return 19999 if turn_color == Board_class.BLACK else -19999

        return 0
    
    '''
    # Compare board1 and board2,
    #   idx: 0=white, 1=black
    #   return 1 if board1 is equal or better than board2,
    #   return 2 if board2 is better than board1
    # {"scores": score, "evaluations": evalv, "critical": False, "checkmate": False, "turns": current_level, "board": self}
    '''
    def compare(self, board1, board2, idx):
        # Checkmate is the best
        if board1["checkmate"]:
            if board2["checkmate"]:
                return 1 if board1["turns"] <= board2["turns"] else 2
            else:
                return 1 if idx == 0 and board1["scores"][1] == 0 else 2
        elif board2["checkmate"]:
            return 2 if idx == 1 and board2["scores"][0] == 0 else 1

        # Positive Critical case
        if board1["critical"] and board1["scores"][idx] > 0:
            if board2["critical"] and board2["scores"][idx] > 0:
                # Large number of score is better
                if board1["scores"][idx] > board2["scores"][idx]:
                    return 1
                
                if board1["scores"][idx] < board2["scores"][idx]:
                    return 2
                
                # Small number of turn is better
                if board1["turns"] < board2["turns"]:
                    return 1
        
                if board1["turns"] > board2["turns"]:
                    return 2
                
                # Large evaluations value is better
                if board1["evaluations"][idx] > board2["evaluations"][idx]:
                    return 1
        
                if board1["evaluations"][idx] < board2["evaluations"][idx]:
                    return 2
            else:
                return 1

        elif board2["critical"] and board2["scores"][idx] > 0:
            return 2

        # Negative Critical case
        if board1["critical"] and board1["scores"][idx] < 0:
            if board2["critical"] and board1["scores"][idx] < 0:
                # Large number of score is better
                if board1["scores"][idx] > board2["scores"][idx]:
                    return 1
                
                if board1["scores"][idx] < board2["scores"][idx]:
                    return 2
                
                # Large number of turn is better
                if board1["turns"] > board2["turns"]:
                    return 1
        
                if board1["turns"] < board2["turns"]:
                    return 2
                
                # Large evaluations value is better
                if board1["evaluations"][idx] > board2["evaluations"][idx]:
                    return 1
        
                if board1["evaluations"][idx] < board2["evaluations"][idx]:
                    return 2
            else:
                return 2

        elif board2["critical"] and board2["scores"][idx] < 0:
            return 1

        # Pieces take preference over candidates
        if Board_class.eval_mode == Board_class.EVAL_MODE_pieces:
            # Large scores value if better
            if board1["scores"][idx] > board2["scores"][idx]:
                return 1
        
            if board1["scores"][idx] < board2["scores"][idx]:
                return 2
            
            # Large candidates value if better
            if board1["candidates"] > board2["candidates"]:
                return 1
        
            if board1["candidates"] < board2["candidates"]:
                return 2

        # Pieces (inverse) take preference over candidates
        elif Board_class.eval_mode == Board_class.EVAL_MODE_pieces_inverse:
            # Little scores value if better
            if board1["scores"][idx] < board2["scores"][idx]:
                return 1
        
            if board1["scores"][idx] > board2["scores"][idx]:
                return 2
            
            # Large candidates value if better
            if board1["candidates"] > board2["candidates"]:
                return 1
        
            if board1["candidates"] < board2["candidates"]:
                return 2
        
        # Candidates take preference over pieces
        else:
            # Large scores value if better
            if board1["scores"][idx] > board2["scores"][idx]:
                return 1
        
            if board1["scores"][idx] < board2["scores"][idx]:
                return 2

            # Large candidates value if better
            if board1["candidates"] > board2["candidates"]:
                return 1
        
            if board1["candidates"] < board2["candidates"]:
                return 2

        # Large evaluations value is better
        if board1["evaluations"][idx] > board2["evaluations"][idx]:
            return 1
        
        if board1["evaluations"][idx] < board2["evaluations"][idx]:
            return 2
        
        # Short turns are better
        if board1["turns"] < board2["turns"]:
            return 1

        return 2
    
    '''
    # Try placing a 'pc' color piece at (px,py) and reverse the opponent piece.
    # (dx,dy) is a direction reversing, (-1,1) = (to left, to bottom of board)
    # Return number of opponent pieces reversed, zero means 'NOT REVERSED AT ALL'
    # If 'reverse' == True, change the board matrix. False, not changed.
    '''
    def do_place(self, px, py, pc, dx, dy, reverse=False):
        # Counter color
        cc = Board_class.WHITE if pc == Board_class.BLACK else Board_class.BLACK

        # Move to next cell
        judge = False
        cx = px + dx
        cy = py + dy
        rv = 0
        while True:
            # Out of board
            if cx < 0 or cx > 7 or cy < 0 or cy > 7:
                break

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
    def place_at(self, px, py, pc, reverse=False):
        if self.board[py][px] != Board_class.BLANK:
            return 0

        rev_total = 0
        for move in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
            rv = self.do_place(px, py, pc, move[0], move[1], reverse)
            if rv > 0:
                rev_total += rv

        return rev_total
    
    '''    
    # Get candidates list of cells to be able to place 'pc' color piece.
    # List of tuple (x, y, numer of opponent cells reversed, evaluation value to put the piece here)
    '''
    def candidates(self, pc):
        cands = []
        for py in list(range(8)):
            for px in list(range(8)):
                if self.board[py][px] == Board_class.BLANK:
                    rv = self.place_at(px, py, pc)
                    if rv > 0:
                        cands.append((px, py, rv, Board_class.eval_put[py][px]))
                    
        return cands

    '''
    # Game over or not?
    # Game over if there is nowhere to place any place .
    '''
    def is_game_over(self):
        w = self.candidates(Board_class.WHITE)
        b = self.candidates(Board_class.BLACK)
        return len(w) + len(b) == 0
        
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
        # Get candidates list to place a piece
        cands = self.candidates(place_color)
        cands_len = len(cands)

        # Get scores and evaluation values of this board
        score = self.scores()
        evalv = self.evaluations()
                        
        # End of tree tracing (reached at maximum thought depth)
        if current_level == Board_class.MAX_DEPTH and turn_color == place_color:
            # Current status data 
            current = {"scores": score, "candidates": cands_len, "evaluations": evalv, "critical": False, "checkmate": False, "turns": current_level, "board": None}

            # Compare this turn's (current) board and the best board upto now 
            if self.compare(current, max_score, 0 if turn_color == Board_class.WHITE else 1) == 1:
                return current
            else:
                return max_score

        # There is nowhere to place it
        if cands_len == 0:
            # Loose
            if turn_color == place_color:
                return None
            # Win
            else:
                return {"scores": score, "candidates": 0, "evaluations": evalv, "critical": False, "checkmate": True, "turns": current_level, "board": None}

        #  Candidates list reduction
        elif cands_len > 1:
            # Sort candidates by evaluation value
            cands.sort(key=lambda can: can[3], reverse=True)
#            cands.sort(key=lambda can: 9999 if (can[0] == 0 or can[0] == 7) and (can[1] == 0 or can[1] == 7) else 0 if (can[0] <= 1 and can[1] <= 1) or (can[0] <= 1 and can[1] >= 6) or (can[0] >= 6 and can[1] <= 1) or (can[0] >= 6 and can[1] >= 6) else can[3], reverse=True)
#            print("SORTED IN DEEP:", cands)

            # Limit to maximum candidates number to decrese possibilities (= calculation time)
            # Remove lower evaluation value.
            if cands_len >= Board_class.LIMIT_CANDIDATES:
                center = int(Board_class.LIMIT_CANDIDATES / 2)
                ev_border = int(cands[0][3] / 2)
                border = 0
                for cand in cands:
                    if border >= center and cand[3] < ev_border:
                        bx = cands[border][0]
                        by = cands[border][1]
                        if Board_class.eval_put[by][bx] == 0:
                            border -= 1

                        cands = cands[0:border]
                        cands_len = len(cands)
                        break
                    
                    border += 1

        # Copy and make new board for simulation
        turn = self.copy("candidate")

        # Trace game trees for each candidate piece to place
        selected_turn = None
        for cand in cands:
            # Board starting next simulation
            turn.set(self)
            cand_score = None
            
            # Place one of candidate piece on the simulation board
            if turn.place_at(cand[0], cand[1], place_color, reverse=True) > 0:
                # name this board
                name = turn.auto_name()

                # This board layout has been evaluated
                if background:
                    if name in Board_class.evaluated_list_bg:
                        print("---CUT SAME PATH (BG):", name)
                        return {"scores": (-899999, -899999), "candidates": cands_len, "evaluations": (-899999, -899999), "critical": False, "checkmate": False, "turns": 0, "board": None}
                    # New board layout in evaluation
                    else:
                        # Board names list sometimes causes memory allocation problem
                        try:
                            Board_class.evaluated_list_bg.append(name)
                        # Avoid memory allocation exception to continue without names list (work slowly)
                        except:
                            print("-----CAN NOT USE NAME LIST (BG)---")
                            Board_class.evaluated_list_bg.clear()
#                            gc.collect()
                else:
                    if name in Board_class.evaluated_list:
                        print("---CUT SAME PATH (FG):", name)
                        return {"scores": (-899999, -899999), "candidates": cands_len, "evaluations": (-899999, -899999), "critical": False, "checkmate": False, "turns": 0, "board": None}
                    # New board layout in evaluation
                    else:
                        # Board names list sometimes causes memory allocation problem
                        try:
                            Board_class.evaluated_list.append(name)
                        # Avoid memory allocation exception to continue without names list (work slowly)
                        except:
                            print("-----CAN NOT USE NAME LIST (FG)---")
                            Board_class.evaluated_list.clear()
                            gc.collect()

                # Board scores
                sc = turn.scores()
                    
                # Checkmate
                if sc[0] == 0:          # white is zero (loose)
                    return {"scores": sc, "candidates": cands_len, "evaluations": (-99999 if turn_color == Board_class.WHITE else 99999, 99999 if turn_color == Board_class.WHITE else -99999), "critical": False, "checkmate": True, "turns": 0, "board": None}
                elif sc[1] == 0:        # black is zero (loose)
                    return {"scores": sc, "candidates": cands_len, "evaluations": (99999 if turn_color == Board_class.WHITE else -99999, -99999 if turn_color == Board_class.WHITE else 99999), "critical": False, "checkmate": True, "turns": 0, "board": None}

                # Take a critical cell
                critical = turn.is_critical_cell(cand[0], cand[1], turn_color, place_color)
                if critical != 0:
                    cl = len(turn.candidates(place_color))
                    # Placing piece is turn color
                    if turn_color == Board_class.WHITE:
                        cand_score =  {"place": (cand[0], cand[1], turn_color, place_color, "deep"), "scores": sc, "candidates": cl, "evaluations": (critical, -critical), "critical": critical > 0, "checkmate": False, "turns": current_level, "board": None}
                    # Placing piece is opponent color
                    else:
                        cand_score = {"place": (cand[0], cand[1], turn_color, place_color, "deep"), "scores": sc, "candidates": cl, "evaluations": (-critical, critical), "critical": critical > 0, "checkmate": False, "turns": current_level, "board": None}

                    # Bad critical, trace deep tree
                    if not cand_score["critical"]:
                        print("***GIVE UP WORST PATH***")
                        max_score = cand_score
                        break
                    '''
                    # Bad critical, trace deep tree
                    if not cand_score["critical]:
                        # Depth first trace for the simulation board
                        cand_score = turn.deep_turn(turn_color, Board_class.BLACK if place_color == Board_class.WHITE else Board_class.WHITE, current_level + (1 if place_color == turn_color else 0), max_score, background)
                    '''
                # Take an ordinally cell
                else:
                    # Depth first trace for the simulation board
                    cand_score = turn.deep_turn(turn_color, Board_class.BLACK if place_color == Board_class.WHITE else Board_class.WHITE, current_level + (1 if place_color == turn_color else 0), max_score, background)

                # Compare the result of simulation board and the best board until now
                if not cand_score is None:
                    # Cut a critical trace pass
                    if cand_score["critical"]:
                        return cand_score

                    if max_score == None:
                        max_score = cand_score
                        max_score["board"] = None
                    else:
                        if self.compare(cand_score, max_score, 0 if turn_color == Board_class.WHITE else 1) == 1:
                            max_score = cand_score
                            max_score["board"] = None

        # garbage collection
        turn.release()
        del turn
#        gc.collect()
        
        # Result
        return max_score


    '''
    # Trace a game tree by recursion call (depth first) for both multi-cores
    # Return a 'best' board information in the possibles.
    #   selected_turn: {"scores": (w,b), "evaluations": (w,b), "checkmate": boolean, "turns": turns to the board, "board": board instance}
    # 'turn_color' is the current game turn's piece color.
    # 'place_color' is the 'my turn' color in simulation board.
    # 'background' = True is for 2nd(sub) core, False is 1st(main) core.
    '''
    def half_turn(self, cands, turn_color, background):
        global othello

        # Tracing tree job
        cands_len = len(cands)
        print("START JOB:", background, cands_len, cands)
        
        # Multi-core process
        if background:
            Board_class.bg_selected_turn = None
            Board_class.bg_working = True
            Board_class.left_cands_bg = cands_len + 1
            print("BACKGROUND:", cands_len)
        else:
            Board_class.left_cands = cands_len + 1

        max_score = None
        for cand in cands:
            # Clear evaluated boards list
            if background:
                Board_class.evaluated_list_bg.clear()
                Board_class.left_cands_bg -= 1
            else:
                Board_class.evaluated_list.clear()
                Board_class.left_cands -= 1

#            gc.collect()

            print("HALF CANDIDATE:", background, cand)
            turn = self.copy("candidate")
            cand_score = None

            # Placed
            if turn.place_at(cand[0], cand[1], turn_color, reverse=True) > 0:
                # Show CPU thought
                if background:
                    Board_class.evaluating_places[1] = (cand[0], cand[1])
                else:
                    Board_class.evaluating_places[0] = (cand[0], cand[1])
                
                # Show the current CPU thought in main core (it seems to have something problems SPI/UART use in 2nd core)
                if not background:
                    display_othello(othello, turn_color)
                    
###DEBUG###                print("HALF PLCE AT:", cand[0], cand[1], turn_color, turn_color, "BG=", background)
                
                # Checkmate
                sc = turn.scores()
                if sc[0] == 0:          # white is zero (loose)
                    if background:
                        Board_class.evaluating_places[1] = (-1, -1)
                    else:
                        Board_class.evaluating_places[0] = (-1, -1)

                    return {"place": (cand[0], cand[1], turn_color, turn_color, "half"), "scores": turn.scores(), "candidates": cands_len, "evaluations": (-99999 if turn_color == Board_class.WHITE else 99999, 99999 if turn_color == Board_class.WHITE else -99999), "critical": False, "checkmate": True, "turns": 0, "board": turn}

                elif sc[1] == 0:        # black is zero (loose)
                    if background:
                        Board_class.evaluating_places[1] = (-1, -1)
                    else:
                        Board_class.evaluating_places[0] = (-1, -1)

                    return {"place": (cand[0], cand[1], turn_color, "half"), "scores": turn.scores(), "candidates": cands_len, "evaluations": (99999 if turn_color == Board_class.WHITE else -99999, -99999 if turn_color == Board_class.WHITE else 99999), "critical": False, "checkmate": True, "turns": 0, "board": turn}
                    
                # Take a critical cell
                critical = turn.is_critical_cell(cand[0], cand[1], turn_color, turn_color)
                if critical != 0:
                    cl = len(turn.candidates(turn_color))
                    # is_critical_cell is lways positive logic
                    # Place white piece at a critical cell
                    if turn_color == Board_class.WHITE:
                        cand_score =  {"place": (cand[0], cand[1], turn_color, turn_color, "half"), "scores": sc, "candidates": cl, "evaluations": (critical, -critical), "critical": critical > 0, "checkmate": False, "turns": 0, "board": turn}
                    # Place black piece at a critical cell
                    else:
                        cand_score =  {"place": (cand[0], cand[1], turn_color, turn_color, "half"), "scores": sc, "candidates": cl, "evaluations": (-critical, critical), "critical": critical > 0, "checkmate": False, "turns": 0, "board": turn}

                    if background:
                        Board_class.bg_selected_turn = cand_score
                        Board_class.evaluating_places[1] = (-1, -1)
                    else:
                        Board_class.evaluating_places[0] = (-1, -1)

                    '''
                    # Bad critical, trace deep tree
                    if not cand_score["critical"]:
                        cand_score = turn.deep_turn(turn_color, Board_class.BLACK if turn_color == Board_class.WHITE else Board_class.WHITE, 1, max_score, background)
###DEBUG###                        print("*****RETURN OF DEEP (CRITICAL):", cand_score, "BG=", background)
                    '''
                # Ordinal cell
                else:
                    # Depth first traverse
                    if max_score is None:
                        # Get scores and evaluation values of this board
                        evalv = turn.evaluations()
                        max_score = {"place": (cand[0], cand[1], turn_color, turn_color, "half"), "scores": sc, "candidates": len(turn.candidates(turn_color)), "evaluations": evalv, "critical": False, "checkmate": False, "turns": 0, "board": turn}

                    cand_score = turn.deep_turn(turn_color, Board_class.BLACK if turn_color == Board_class.WHITE else Board_class.WHITE, 1, max_score, background)
###DEBUG###                    print("*****RETURN OF DEEP(ORDINAL):", cand_score, "BG=", background)

                # Choose best cell
                if not cand_score is None:
                    if max_score is None:
                        max_score = cand_score
                        max_score["board"] = turn
                    else:
                        if self.compare(cand_score, max_score, 0 if turn_color == Board_class.WHITE else 1) == 1:
#                            max_score["board"].release()
#                            del max_score["board"]
                            max_score = cand_score
                            max_score["board"] = turn
                            
                # No candidate
                else:
                    turn.release()
                    del turn

            # There is noweher to place a piece
            else:
                turn.release()
                del turn
                
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
        print("***DECIDED HALF:", max_score, "BG=", background)
        return max_score


    '''
    # A resident program to think game strategy in mlti-core.
    # When Board_class.bg_cands has a candidates list,  this program runs.
    '''
    def half_turn_multi_core(self):
        global othello

        # Loop during be terminated (NOT SUPPORT CURRENTLY)
        while not Board_class.bg_terminate:
            # Wait for next job
            while Board_class.bg_cands is None:
                time.sleep(0.1)

            # Done a job, go to waiting mode
            self.half_turn(Board_class.bg_cands, Board_class.bg_turn_color, True)
            Board_class.bg_cands = None
            Board_class.bg_turn_color = Board_class.BLANK
            Board_class.bg_working = False

        Board_class.bg_wakeup = False


    '''
    # Start multi-core process (half_turn_multi_core)
    '''
    def start_multi_core(self):
        if not Board_class.bg_wakeup:
            try:
                Board_class.bg_wakeup = True
                res_thread = _thread.start_new_thread(self.half_turn_multi_core, ())
                print("START MULTI-CORE.")
            except Exception as e:
                Board_class.bg_wakeup = False
                print("COULD NOT START MULTI-CORE.")
                print("EXCEPTION = ", e)
        
        return Board_class.bg_wakeup

    '''
    # Decied a next turn board from some candidates to place a piece
    # by tracing game tree in possibles and return the best result.
    # If there are some candidates to place a piece, use malti-core.
    # 'turn_color' is the color of the current turn (white or black)
    '''
    def next_turn(self, turn_color):
        global othello

        gc.collect()
        Board_class.left_cands = 0
        Board_class.left_cands_bg = 0

        # Get cells being able to place a piece
        cands = self.candidates(turn_color)
        cands_len = len(cands)
        print("CANDIDATES[", cands_len, "] = ", cands)

        # No cell to place it
        if cands_len == 0:
            # Loose
            return None
        
        # Only one candidate
        elif cands_len == 1:
            # Copy and make new board and place a piece at a candidate cell
            turn = self.copy("candidate")
            turn.place_at(cands[0][0], cands[0][1], turn_color, reverse=True)
            score = turn.scores()
            evalv = turn.evaluations()                
            return {"scores": score, "candidates": cands_len, "evaluations": evalv, "critical": False, "checkmate": False, "turns": 1, "board": turn}            

        # Candidates list reduction
#        elif cands_len > 1:
        else:
            # Sort candidates by evaluation value
            cands.sort(key=lambda can: can[3], reverse=True)
###DEBUG###            print("SORTED:", cands)

            # Limit to maximum candidates number to decrese possibilities (= calculation time)
            # Remove lower evaluation value.
            if cands_len >= Board_class.LIMIT_CANDIDATES:
                center = int(Board_class.LIMIT_CANDIDATES / 2)
                ev_border = int(cands[0][3] / 2)
                border = 0
                for cand in cands:
                    if border >= center and cand[3] < ev_border:
                        # Take even number of candidates for dual core cpus
                        if (border % 2) == 1 and border + 1 < cands_len:
                            border += 1
                            bx = cands[border][0]
                            by = cands[border][1]
                            if Board_class.eval_put[by][bx] == 0:
                                border -= 1

                        cands = cands[0:border]
                        cands_len = len(cands)
                        break
                    
                    border += 1

            print("LIMITED:", cands)
        
        # Candidates list
        # Divide the candidate list into two lists
        h = int(cands_len/2)
        cands1 = cands[0:h]
        cands2 = cands[h:cands_len]

        # Clear multi-core result
        Board_class.bg_selected_turn = None
        gc.collect()
        print("GC FREE MEMORY=", gc.mem_free())

        if self.start_multi_core():
            Board_class.bg_working = True
            Board_class.bg_turn_color = turn_color
            Board_class.bg_cands = cands2
        else:
            Board_class.bg_working = False
            Board_class.bg_cands = None
            Board_class.bg_turn_color = Board_class.BLANK
            print("MULTI-CORE DOSE NOT WORK. USE ONLY MAIN CORE")
            cands1 += cands2

        # Candidates list-1 is traced with main core
        selected_turn = self.half_turn(cands1, turn_color, False)
        Board_class.left_cands = 0
        
        # Wait for end of multi-core job
###DEBUG###        print("WAIT FOR BG-JOB:", Board_class.bg_working)
        while Board_class.bg_working:
            # Show 2nd CPU thought
            display_othello(othello, turn_color)
            time.sleep(1)
                
        Board_class.left_cands_bg = 0
        print("=======JOIN MULTI-CORES.=======")
        print("CORE0:", selected_turn)
        print("CORE1:", Board_class.bg_selected_turn)
        
        # Compare the results of main-core and multi-core
        if not selected_turn is None:
            if not Board_class.bg_selected_turn is None:
                if self.compare(selected_turn, Board_class.bg_selected_turn, 0 if turn_color == Board_class.WHITE else 1) == 2:
                    selected_turn["board"].release()
                    del selected_turn["board"]
                    selected_turn = Board_class.bg_selected_turn
                    selected_turn["board"] = Board_class.bg_selected_turn["board"]
                    
        elif not Board_class.bg_selected_turn is None:
            selected_turn["board"].release()
            del selected_turn["board"]
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
                          0b100101000,
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
def display_othello(othello, next_turn):
    global LCD, GT, in_display_othello
    
    if in_display_othello:
        return

    in_display_othello = True

    while LCD.cs() == 0 or LCD.tp_cs() == 0:
###DEBUG###        print("+++WAITING FOR SPI in display+++")
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
                GT.show_graphic_text(str(Board_class.LIMIT_CANDIDATES), 3, 25, 2, 2, 0, col, LCD.BROWN)
                GT.show_graphic_text("C", 26, 20, 3, 3, 0, col, LCD.BROWN)
                GT.show_graphic_text(str(Board_class.MAX_DEPTH), 57, 25, 2, 2, 0, col, LCD.BROWN)
            else:
                GT.show_graphic_text("M", 26, 20, 3, 3, 0, col, LCD.BROWN)
            
            GT.show_graphic_text("MC", 410,  3, 3, 3, 5, LCD.YELLOW if vs == 1 else LCD.ORANGE, LCD.BROWN)
            GT.show_graphic_text("CM", 410, 43, 3, 3, 5, LCD.YELLOW if vs == 2 else LCD.ORANGE, LCD.BROWN)
            
            if game_over:
                if score[0] > score[1]:
                    GT.show_graphic_text("W", 26, 50, 3, 3, 0, col, LCD.BROWN)
                elif score[0] < score[1]:
                    GT.show_graphic_text("L", 26, 50, 3, 3, 0, col, LCD.BROWN)
                else:
                    GT.show_graphic_text("D", 26, 50, 3, 3, 0, col, LCD.BROWN)
            elif next_turn == Board_class.WHITE:
                if len(candw) == 0:
                    GT.show_graphic_text("P" , 26, 50, 3, 3, 0, col, LCD.BROWN)
                else:
                    GT.show_graphic_text("*" , 26, 50, 3, 3, 0, col, LCD.BROWN)
                    
        # White score
        elif row == 1:
            sc = str(score[0])
            if len(sc) == 1:
                sc = " " + sc

            GT.show_graphic_text(sc , 10, 10, 3, 6, 2, LCD.WHITE, LCD.BROWN)
            
            GT.show_graphic_text("CC", 410,  3, 3, 3, 5, LCD.YELLOW if vs == 3 else LCD.ORANGE, LCD.BROWN)
            GT.show_graphic_text("MM", 410, 43, 3, 3, 5, LCD.YELLOW if vs == 0 else LCD.ORANGE, LCD.BROWN)
        
        # Black score
        elif row == 2:
            sc = str(score[1])
            if len(sc) == 1:
                sc = " " + sc
            
            GT.show_graphic_text(sc , 10, 20, 3, 6, 2, LCD.BLACK, LCD.BROWN)
            if Board_class.in_play:
                GT.show_graphic_text("UD", 410, 43, 3, 3, 5, LCD.PINK, LCD.BROWN)
            else:
                GT.show_graphic_text("PL", 410, 43, 3, 3, 5, LCD.MINT, LCD.BROWN)

            if Board_class.in_play:
                if Board_class.bg_working:
                    GT.show_graphic_text("S" + str(Board_class.left_cands) + "M" + str(Board_class.left_cands_bg), 410, 13, 1, 1, 3, LCD.MINT, LCD.BROWN)
                elif Board_class.left_cands > 0:
                    GT.show_graphic_text("S" + str(Board_class.left_cands), 410, 13, 1, 1, 2, LCD.MINT, LCD.BROWN)

        # Black turn
        elif row == 3:
            col = LCD.BLACK if Board_class.black_is_cpu else LCD.YELLOW
            if Board_class.black_is_cpu:
                GT.show_graphic_text(str(Board_class.LIMIT_CANDIDATES), 3, 40, 2, 2, 0, col, LCD.BROWN)
                GT.show_graphic_text("C", 26, 35, 3, 3, 0, col, LCD.BROWN)
                GT.show_graphic_text(str(Board_class.MAX_DEPTH), 57, 40, 2, 2, 0, col, LCD.BROWN)
            else:
                GT.show_graphic_text("M", 26, 35, 3, 3, 0, col, LCD.BROWN)

            GT.show_graphic_text("RS", 410, 43, 3, 3, 5, LCD.PINK if Board_class.in_play else LCD.BLACK, LCD.BROWN)

            if game_over:
                if score[0] < score[1]:
                    GT.show_graphic_text("W", 26, 3, 3, 3, 0, col, LCD.BROWN)
                elif score[0] > score[1]:
                    GT.show_graphic_text("L", 26, 3, 3, 3, 0, col, LCD.BROWN)
                else:
                    GT.show_graphic_text("D", 26, 3, 3, 3, 0, col, LCD.BROWN)
            elif next_turn == Board_class.BLACK:
                if len(candb) == 0:
                    GT.show_graphic_text("P" , 26, 3, 3, 3, 0, col, LCD.BROWN)
                else:
                    GT.show_graphic_text("*" , 26, 3, 3, 3, 0, col, LCD.BROWN)
            
        # Cells
        y = 0
        for dy in list(range(2)):
            x = 80
            for dx in list(range(8)):
                LCD.fill_rect(x, y, cell_size, cell_size, LCD.GREEN)
                c = othello.board[row*2+dy][dx]
                if c != Board_class.BLANK:
                    LCD.ellipse(x + cell_half, y + cell_half, cell_half - 4, cell_half - 4, LCD.WHITE if c == Board_class.WHITE else LCD.BLACK, True)

                LCD.rect(x, y, cell_size, cell_size, LCD.BROWN)
                LCD.rect(x+1, y+1, cell_size-2, cell_size-2, LCD.BROWN)
                x += cell_size

            y += cell_size
            
        # Evaluationg cell by main-core if exists
        if Board_class.evaluating_places[0][0] != -1:
            ex = Board_class.evaluating_places[0][0]
            ey = Board_class.evaluating_places[0][1]
            if row*2 <= ey and ey <= row*2+1:
                ey = ey % 2
                LCD.ellipse(ex * cell_size + cell_half + 80, ey * cell_size + cell_half, cell_half - 4, cell_half - 4, LCD.RED, True)
        
        # Evaluationg cell by multi-core if exists
        if Board_class.evaluating_places[1][0] != -1:
            ex = Board_class.evaluating_places[1][0]
            ey = Board_class.evaluating_places[1][1]
            if row*2 <= ey and ey <= row*2+1:
                ey = ey % 2
                LCD.ellipse(ex * cell_size + cell_half + 80, ey * cell_size + cell_half, cell_half - 4, cell_half - 4, LCD.MAGENTA, True)

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
    global LCD, LCD_touch_x, LCD_touch_y, in_timer_func

    if in_timer_func:
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
            if othello.place_at(cx, cy, player) > 0:
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
###DEBUG###        print("+++WAITING FOR SPI in touch+++")
        time.sleep(0.1)

    # Wait for touch screen
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
            time.sleep(0.1)
        
        # Do a touch action
        if not X_Point is None and not Y_Point is None:
            res_touch = touch_action(othello, X_Point, Y_Point, player)
            
            # Touch something
            if not res_touch is None:
                (x, y) = res_touch

                # Touch a cell which a piece can place there
                if 0 <= x and x <= 7 and 0 <= y and y <= 7:
                    # Save board for undo
#                    print("SAVE UNDO")
                    undo_board.set(othello)
#                    undo_board.dump()
                    
                    # Place a piece
                    othello.place_at(x, y, player, True)
                    ret = 0
                    break
                
                # Undo button
                elif x == -2 and y == -2:
                    if not undo_board is None:
###DEBUG###                        print("UNDO")
                        undo_board.dump()
                        othello.set(undo_board)
                        
                        # redraw
                        while in_display_othello:
                            time.sleep(0.1)
                            
                        display_othello(othello, Board_class.WHITE if player == Board_class.BLACK else Board_class.WHITE)

                # Reset button
                else:
                    ret = -1
                    break
        
        time.sleep(0.1)
    
    return ret


'''
# Select game mode.
#   MC: Human vs CPU, CM: CPU vs Human, CC: CPU vs CPU, MM:Human vs Human
#   PL: Start playing a game.
'''
def select_game_mode():
    global LCD, LCD_touch_x, LCD_touch_y, in_timer_func

    while LCD.cs() == 0 or LCD.tp_cs() == 0:
###DEBUG###        print("+++WAITING FOR SPI in mode+++")
        time.sleep(0.1)

    print("===SELECT GAME MODE then PLAY===")
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
    Board_class.eval_put = Board_class.EVAL_PUT0
    othello.restart([(3,3),(4,4)], [(4,3),(3,4)])
    othello.dump()
    
    # Undo object
    undo_board = Board_class("undo_board")
    undo_board.set(othello)

    # Game loop
    while True:
        # Initialize the board
        Board_class.in_play = False
        display_othello(othello, Board_class.WHITE)

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
        turn = 0
        pass_num = 0
        othello.restart([(3,3),(4,4)], [(4,3),(3,4)])
        undo_board.set(othello)
        display_othello(othello, Board_class.WHITE)
        
        # Thought depth control
        Board_class.LIMIT_CANDIDATES = 8
        Board_class.MAX_DEPTH = 2

#        Board_class.eval_mode = Board_class.EVAL_MODE_pieces
        Board_class.eval_mode = Board_class.EVAL_MODE_pieces_inverse

        while pass_num < 2:
            # Thought depth control
            if turn == 16:
                Board_class.LIMIT_CANDIDATES = 8
                Board_class.MAX_DEPTH = 3

#                Board_class.eval_mode = Board_class.EVAL_MODE_pieces
                Board_class.eval_mode = Board_class.EVAL_MODE_pieces_inverse

                ev = othello.evaluations()
            elif turn == 24:
                Board_class.LIMIT_CANDIDATES = 10
                Board_class.MAX_DEPTH = 3

#                Board_class.eval_mode = Board_class.EVAL_MODE_pieces
                Board_class.eval_mode = Board_class.EVAL_MODE_pieces_inverse
#                ev = othello.evaluations()
            elif turn == 36: 
                Board_class.LIMIT_CANDIDATES = 10
                Board_class.MAX_DEPTH = 7

                Board_class.eval_mode = Board_class.EVAL_MODE_pieces
#                Board_class.eval_mode = Board_class.EVAL_MODE_pieces_inverse
#                ev = othello.evaluations()
            elif turn == 40:
                Board_class.LIMIT_CANDIDATES = 10
                Board_class.MAX_DEPTH = 6

                Board_class.eval_mode = Board_class.EVAL_MODE_pieces
#                Board_class.eval_mode = Board_class.EVAL_MODE_pieces_inverse
#                ev = othello.evaluations()
        
            # White turn
            turn += 1
        
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
                    max_score["board"].dump()
                    othello.set(max_score["board"])
                    max_score["board"].release()
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
                    othello.dump()
                    
                # Reset button
                elif res_man == -1:
                    print("===RESET===")
                    break

            # Redraw
            Board_class.evaluating_places[1] = (-1, -1)
            Board_class.evaluating_places[0] = (-1, -1)
            while in_display_othello:
                time.sleep(0.1)
            display_othello(othello, Board_class.BLACK)

            # Black turn
            turn += 1
        
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
                    max_score["board"].dump()
                    othello.set(max_score["board"])

                    max_score["board"].release()
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
                    othello.dump()
                    
                # Reset button
                elif res_man == -1:
                    print("===RESET===")
                    break

            # Redraw
            Board_class.evaluating_places[1] = (-1, -1)
            Board_class.evaluating_places[0] = (-1, -1)
            while in_display_othello:
                time.sleep(0.1)
            display_othello(othello, Board_class.WHITE)

        # Show scores
        score = othello.scores()
        print("GAME RESULT: WHITE=", score[0], "/ BLACK=", score[1])
    

