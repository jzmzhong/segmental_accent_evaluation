#!/usr/bin/env python3

from Aligner import Aligner
from pl_table import pl_table

aligner = Aligner( pl_table )

# print(aligner.doAlignment( 'ax0 b ae1 n d ax0 n'.split(), 'abandon' ))
# print(aligner.doAlignment( 'k ax0 m p l eh1 k s ax0 t iy0'.split(), 'complexity' ))
# print(aligner.doAlignment( 'k ax0 m ow1 sh ax0 n'.split(), 'commotion' ))
# print(aligner.doAlignment( 'ax0'.split(), 'aaaaa' ))
# print(aligner.doAlignment( 'ax0 ax0 ax0 ax0'.split(), "aa" ))
# print(aligner.doAlignment( 'ah0'.split(), "a" ))
# print(aligner.doAlignment(['d', 'ay2', 'ah0', 'g', 'n', 'ow1', 's', 'ah0', 's'], 'diagnosis' ))
# print(aligner.doAlignment( 'ax0 b ae1 n d ax0 n'.split(), 'abandon' ))
print(aligner.doAlignment( 's eh1 r ah0'.split(), 'sarah' ))
print(aligner.doAlignment( 'v eh1 t r ah0 n eh2 r iy0'.split(), 'veterinary' ))
print(aligner.doAlignment( 'ow1 v er0 k ah m ih0 ng'.split(), 'overcoming' ))