#!/usr/bin/env python
###########################################################################
##                                                                       ##
##                Centre for Speech Technology Research                  ##
##                   (Edinburgh University, UK) and                      ##
##                           Korin Richmond                              ##
##                         Copyright (c) 2006                            ##
##                         All Rights Reserved.                          ##
##                                                                       ##
##  Permission is hereby granted, free of charge, to use and distribute  ##
##  this software and its documentation without restriction, including   ##
##  without limitation the rights to use, copy, modify, merge, publish,  ##
##  distribute, sublicense, and/or sell copies of this work, and to      ##
##  permit persons to whom this work is furnished to do so, subject to   ##
##  the following conditions:                                            ##
##                                                                       ##
##   1. The code must retain the above copyright notice, this list of    ##
##      conditions and the following disclaimer.                         ##
##   2. Any modifications must be clearly marked as such.                ##
##   3. Original authors' names are not deleted.                         ##
##   4. The authors' names are not used to endorse or promote products   ##
##      derived from this software without specific prior written        ##
##      permission.                                                      ##
##                                                                       ##
##  EDINBURGH UNIVERSITY AND THE CONTRIBUTORS TO THIS WORK DISCLAIM      ##
##  ALL WARRANTIES WITH REGARD TO THIS SOFTWARE, INCLUDING ALL           ##
##  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT       ##
##  SHALL EDINBURGH UNIVERSITY OR THE CONTRIBUTORS BE LIABLE FOR         ##
##  ANY SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES        ##
##  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER      ##
##  IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,       ##
##  ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF       ##
##  THIS SOFTWARE.                                                       ##
##                                                                       ##
###########################################################################
##                                                                       ##
##  Class to find most probable alignment of two lists of symbols given  ##
##  a table of symbol match probabilities                                ##
##                                                                       ##
## AUTHOR: KORIN RICHMOND                                                ##
## DATE:   28/07/2006                                                    ##
###########################################################################

import json
from pathlib import Path


class Aligner:
    def __init__( self, probdict, exceptions_file=None ):
        self.reset()
        self.probtable = probdict
        if exceptions_file is None:
            exceptions_file = Path(__file__).with_name('exceptions.json')
        if exceptions_file.exists():
            with open(exceptions_file, encoding='utf-8') as file_handle:
                self.exceptions = json.load(file_handle)
        else:
            self.exceptions = {}

    def reset( self ):
        self.best_score = 0.0
        self.best_path = []
        
    def scoreMatch( self, symA, symB ):
        symB_probdict = self.probtable[symB]
        try:
            score = symB_probdict[symA]
            isValidMatch = True
        except KeyError:
            score = 0
            isValidMatch = False

        return score, isValidMatch

    def doAlignment( self, symlistA, symlistB ):
        exception = self.exceptions.get(symlistB)
        if exception:
            if type(exception) is list:
                return [list(pair) for pair in exception]
            elif type(exception) is dict:
                key = " ".join(symlistA)
                if key in exception:
                    return [list(pair) for pair in exception[key]]
        
        self.reset()
        self.find_best_alignment( symlistA, symlistB, [], 0.0 )
        self.best_path.reverse()
        return self.best_path


    def find_best_alignment( self, symlistA, symlistB, path, score ):
        if len(symlistB)==0:
            if len(symlistA) == 0 and score > self.best_score: # terminate when all phones are consumed
            # if score > self.best_score:
                self.best_score = score
                self.best_path = path
            return
        
        symB = symlistB[0]
        symlistA_len = len(symlistA)

        # symB -> no symA
        (matchScore, matchIsValid) = self.scoreMatch( '_epsilon_', symB )
        if matchIsValid:
            self.find_best_alignment( symlistA, symlistB[1:], 
                                    [['_epsilon_', symB]]+path, score+float(matchScore) )  

        # symB -> one symA 
        if symlistA_len != 0:
            (matchScore, matchIsValid) = self.scoreMatch( symlistA[0], symB )
            if matchIsValid:
                self.find_best_alignment( symlistA[1:], symlistB[1:],
                                        [[symlistA[0], symB]]+path, score+float(matchScore) )

        # symB -> two symlistA symbols
        if symlistA_len > 1:
            tn = "%s-%s" % (symlistA[0], symlistA[1])
            (matchScore, matchIsValid) = self.scoreMatch( tn, symB )
            if matchIsValid:
                self.find_best_alignment( symlistA[2:], symlistB[1:], 
                                         [[tn, symB]]+path, score+float(matchScore) )

        # symB -> three symlistA symbols
        if symlistA_len > 2:
            tn = "%s-%s-%s" % (symlistA[0], symlistA[1], symlistA[2])
            (matchScore, matchIsValid) = self.scoreMatch( tn, symB )
            if matchIsValid:
                self.find_best_alignment( symlistA[3:], symlistB[1:], 
                                         [[tn, symB]]+path, score+float(matchScore) )
