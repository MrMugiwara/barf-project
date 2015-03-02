import os
import pickle
import random
import unittest
import struct

import pyasmjit

from barf.analysis.codeanalyzer import CodeAnalyzer
from barf.analysis.gadget.gadget import GadgetType
from barf.analysis.gadget.gadgetclassifier import GadgetClassifier
from barf.analysis.gadget.gadgetfinder import GadgetFinder
from barf.analysis.gadget.gadgetverifier import GadgetVerifier
from barf.arch.arm.armbase import ArmArchitectureInformation
from barf.arch.arm.armtranslator import ArmTranslator
from barf.arch.arm.armdisassembler import ArmDisassembler
from barf.arch import ARCH_ARM_MODE_32
from barf.arch.arm.armtranslator import FULL_TRANSLATION
from barf.arch.arm.armtranslator import LITE_TRANSLATION
from barf.arch.arm.armparser import ArmParser
from barf.core.reil import ReilEmulator
from barf.core.smt.smtlibv2 import Z3Solver as SmtSolver
from barf.core.smt.smttranslator import SmtTranslator
from barf.core.reil import ReilEmptyOperand
from barf.core.reil import ReilEmulator
from barf.core.reil import ReilImmediateOperand
from barf.core.reil import ReilRegisterOperand


class ArmGadgetClassifierTests(unittest.TestCase):

    def setUp(self):

        self._arch_info = ArmArchitectureInformation(ARCH_ARM_MODE_32)
        self._smt_solver = SmtSolver()
        self._smt_translator = SmtTranslator(self._smt_solver, self._arch_info.address_size)
        self._ir_emulator = ReilEmulator(self._arch_info.address_size)

        self._ir_emulator.set_arch_registers(self._arch_info.registers_gp_all)
        self._ir_emulator.set_arch_registers_size(self._arch_info.registers_size)
        self._ir_emulator.set_reg_access_mapper(self._arch_info.registers_access_mapper())

        self._smt_translator.set_reg_access_mapper(self._arch_info.registers_access_mapper())
        self._smt_translator.set_arch_registers_size(self._arch_info.registers_size)

        self._code_analyzer = CodeAnalyzer(self._smt_solver, self._smt_translator)

        self._g_classifier = GadgetClassifier(self._ir_emulator, self._arch_info)
        self._g_verifier = GadgetVerifier(self._code_analyzer, self._arch_info)

    def _find_and_classify_gadgets(self, binary):
        g_finder = GadgetFinder(ArmDisassembler(), binary, ArmTranslator(translation_mode=LITE_TRANSLATION))

        g_candidates = g_finder.find_arm(0x00000000, len(binary), instrs_depth=4)
        g_classified = self._g_classifier.classify(g_candidates[0])

#         self._print_candidates(g_candidates)
#         self._print_classified(g_classified)

        return g_candidates, g_classified

    def test_move_register_1(self):
        # testing : dst_reg <- src_reg
        binary  = "\x04\x00\xa0\xe1"                     # 0x00 : (4)  mov    r0, r4
        binary += "\x31\xff\x2f\xe1"                     # 0x04 : (4)  blx    r1

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.MoveRegister)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r4", 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r0", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_move_register_2(self):
        # testing : dst_reg <- src_reg
        binary  = "\x00\x00\x84\xe2"                     # 0x00 : (4)  add    r0, r4, #0
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr
#         binary += "\x00\x80\xbd\xe8"                     # 0x04 : (4)  pop     {pc} # TODO: Not supported yet because it's not an excplicit jump


        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.MoveRegister)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r4", 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r0", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    # TODO: test_move_register_n: mul r0, r4, #1

    def test_load_constant_1(self):
        # testing : dst_reg <- constant
        binary  = "\x0a\x20\xa0\xe3"                     # 0x00 : (4)  mov    r2, #10
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.LoadConstant)
        self.assertEquals(g_classified[0].sources, [ReilImmediateOperand(10, 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r2", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)
        self.assertFalse(ReilRegisterOperand("r2", 32) in g_classified[0].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_load_constant_2(self):
        # testing : dst_reg <- constant
        binary  = "\x02\x20\x42\xe0"                     # 0x00 : (4)  sub    r2, r2, r2
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.LoadConstant)
        self.assertEquals(g_classified[0].sources, [ReilImmediateOperand(0, 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r2", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)
        self.assertFalse(ReilRegisterOperand("r2", 32) in g_classified[0].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_load_constant_3(self):
        # testing : dst_reg <- constant
        binary  = "\x02\x20\x22\xe0"                     # 0x00 : (4)  eor    r2, r2, r2
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.LoadConstant)
        self.assertEquals(g_classified[0].sources, [ReilImmediateOperand(0, 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r2", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)
        self.assertFalse(ReilRegisterOperand("r2", 32) in g_classified[0].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_load_constant_4(self):
        # testing : dst_reg <- constant
        binary  = "\x00\x20\x02\xe2"                     # 0x00 : (4)  and    r2, r2, #0
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.LoadConstant)
        self.assertEquals(g_classified[0].sources, [ReilImmediateOperand(0, 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r2", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)
        self.assertFalse(ReilRegisterOperand("r2", 32) in g_classified[0].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_load_constant_5(self):
        # testing : dst_reg <- constant
        binary  = "\x00\x20\x02\xe2"                     # and    r2, r2, #0
        binary += "\x21\x20\x82\xe3"                     # orr    r2, r2, #33
        binary += "\x1e\xff\x2f\xe1"                     # bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.LoadConstant)
        self.assertEquals(g_classified[0].sources, [ReilImmediateOperand(33, 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r2", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)
        self.assertFalse(ReilRegisterOperand("r2", 32) in g_classified[0].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_arithmetic_add_1(self):
        # testing : dst_reg <- src1_reg + src2_reg
        binary  = "\x08\x00\x84\xe0"                     # 0x00 : (4)  add    r0, r4, r8
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.Arithmetic)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r4", 32), ReilRegisterOperand("r8", 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r0", 32)])
        self.assertEquals(g_classified[0].operation, "+")

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_arithmetic_sub_1(self):
        # testing : dst_reg <- src1_reg + src2_reg
        binary  = "\x08\x00\x44\xe0"                     # 0x00 : (4)  sub    r0, r4, r8
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.Arithmetic)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r4", 32), ReilRegisterOperand("r8", 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r0", 32)])
        self.assertEquals(g_classified[0].operation, "-")

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_load_memory_1(self):
        # testing : dst_reg <- m[src_reg]
        binary  = "\x00\x30\x94\xe5"                     # 0x00 : (4)  ldr    r3, [r4]
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.LoadMemory)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x0, 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r3", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_load_memory_2(self):
        # testing : dst_reg <- m[src_reg + offset]
        binary  = "\x33\x30\x94\xe5"                     # 0x00 : (4)  ldr    r3, [r4 + 0x33]
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.LoadMemory)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x33, 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r3", 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    # TODO: ARM's ldr rd, [rn, r2] is not a valid classification right now

    def test_store_memory_1(self):
        # testing : dst_reg <- m[src_reg]
        binary  = "\x00\x30\x84\xe5"                     # 0x00 : (4)  str    r3, [r4]
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.StoreMemory)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r3", 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x0, 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_store_memory_2(self):
        # testing : dst_reg <- m[src_reg + offset]
        binary  = "\x33\x30\x84\xe5"                     # 0x00 : (4)  str    r3, [r4 + 0x33]
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 1)

        self.assertEquals(g_classified[0].type, GadgetType.StoreMemory)
        self.assertEquals(g_classified[0].sources, [ReilRegisterOperand("r3", 32)])
        self.assertEquals(g_classified[0].destination, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x33, 32)])

        self.assertEquals(len(g_classified[0].modified_registers), 0)

        self.assertTrue(self._g_verifier.verify(g_classified[0]))

    def test_arithmetic_load_add_1(self):
        # testing : dst_reg <- dst_reg + mem[src_reg]
        binary  = "\x00\x30\x94\xe5"                     # 0x00 : (4)  ldr    r3, [r4]
        binary += "\x03\x00\x80\xe0"                     # 0x00 : (4)  add    r0, r0, r3
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 2)

        self.assertEquals(g_classified[1].type, GadgetType.ArithmeticLoad)
        self.assertEquals(g_classified[1].sources, [ReilRegisterOperand("r0", 32), ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x0, 32)])
        self.assertEquals(g_classified[1].destination, [ReilRegisterOperand("r0", 32)])
        self.assertEquals(g_classified[1].operation, "+")

        self.assertEquals(len(g_classified[1].modified_registers), 1)

        self.assertFalse(ReilRegisterOperand("r0", 32) in g_classified[1].modified_registers)
        self.assertTrue(ReilRegisterOperand("r3", 32) in g_classified[1].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[1]))

    def test_arithmetic_load_add_2(self):
        # testing : dst_reg <- dst_reg + mem[src_reg + offset]
        binary  = "\x22\x30\x94\xe5"                     # 0x00 : (4)  ldr    r3, [r4, 0x22]
        binary += "\x03\x00\x80\xe0"                     # 0x00 : (4)  add    r0, r0, r3
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 2)

        self.assertEquals(g_classified[1].type, GadgetType.ArithmeticLoad)
        self.assertEquals(g_classified[1].sources, [ReilRegisterOperand("r0", 32), ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x22, 32)])
        self.assertEquals(g_classified[1].destination, [ReilRegisterOperand("r0", 32)])
        self.assertEquals(g_classified[1].operation, "+")

        self.assertEquals(len(g_classified[1].modified_registers), 1)

        self.assertFalse(ReilRegisterOperand("r0", 32) in g_classified[1].modified_registers)
        self.assertTrue(ReilRegisterOperand("r3", 32) in g_classified[1].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[1]))

    def test_arithmetic_store_add_1(self):
        # testing : m[dst_reg] <- m[dst_reg] + src_reg
        binary  = "\x00\x30\x94\xe5"                     # 0x00 : (4)  ldr    r3, [r4]
        binary += "\x03\x30\x80\xe0"                     # 0x00 : (4)  add    r3, r0, r3
        binary += "\x00\x30\x84\xe5"                     # 0x00 : (4)  str    r3, [r4]
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 2)

        self.assertEquals(g_classified[1].type, GadgetType.ArithmeticStore)
        self.assertEquals(g_classified[1].sources, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x0, 32), ReilRegisterOperand("r0", 32)])
        self.assertEquals(g_classified[1].destination, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x0, 32)])
        self.assertEquals(g_classified[1].operation, "+")

        self.assertEquals(len(g_classified[1].modified_registers), 1)

        self.assertFalse(ReilRegisterOperand("r4", 32) in g_classified[1].modified_registers)
        self.assertTrue(ReilRegisterOperand("r3", 32) in g_classified[1].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[1]))

    def test_arithmetic_store_add_2(self):
        # testing : dst_reg <- dst_reg + mem[src_reg + offset]
        binary  = "\x22\x30\x94\xe5"                     # 0x00 : (4)  ldr    r3, [r4, 0x22]
        binary += "\x03\x30\x80\xe0"                     # 0x00 : (4)  add    r3, r0, r3
        binary += "\x22\x30\x84\xe5"                     # 0x00 : (4)  str    r3, [r4, 0x22]
        binary += "\x1e\xff\x2f\xe1"                     # 0x04 : (4)  bx     lr

        g_candidates, g_classified = self._find_and_classify_gadgets(binary)

        self.assertEquals(len(g_candidates), 1)
        self.assertEquals(len(g_classified), 2)

        self.assertEquals(g_classified[1].type, GadgetType.ArithmeticStore)
        self.assertEquals(g_classified[1].sources, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x22, 32), ReilRegisterOperand("r0", 32)])
        self.assertEquals(g_classified[1].destination, [ReilRegisterOperand("r4", 32), ReilImmediateOperand(0x22, 32)])
        self.assertEquals(g_classified[1].operation, "+")

        self.assertEquals(len(g_classified[1].modified_registers), 1)

        self.assertFalse(ReilRegisterOperand("r4", 32) in g_classified[1].modified_registers)
        self.assertTrue(ReilRegisterOperand("r3", 32) in g_classified[1].modified_registers)

        self.assertTrue(self._g_verifier.verify(g_classified[1]))

    def _print_candidates(self, candidates):
        print "Candidates :"

        for g in candidates:
            print g
            print "-" * 10

    def _print_classified(self, classified):
        print "Classified :"

        for g in classified:
            print g
            print g.type
            print "-" * 10


def main():
    unittest.main()


if __name__ == '__main__':
    main()
