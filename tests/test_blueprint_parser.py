import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from blueprint_parser import BlueprintParser, format_ast_markdown, parse_sexpr, summarize_dsl, tokenize_dsl


class TestBlueprintParser(unittest.TestCase):
    def test_tokenize_and_parse_sexpr(self):
        text = """
        ; Comment here
        (event Custom|DoSomething (Param1 "string with spaces")
          (bind myVar 42)
          (Widget|SetVisibility :Visibility "Collapsed"))
        """
        tokens = tokenize_dsl(text)
        self.assertIn('event', tokens)
        self.assertIn('Custom|DoSomething', tokens)
        self.assertIn('"string with spaces"', tokens)
        self.assertNotIn('; Comment here', tokens)

        trees = parse_sexpr(tokens)
        self.assertEqual(len(trees), 1)
        self.assertEqual(trees[0][0], 'event')
        self.assertEqual(trees[0][1], 'Custom|DoSomething')

    def test_parse_simple_function(self):
        dsl = """
        (fn DoubleIt (Value)
          (return (* Value 2)))
        """
        parser = BlueprintParser()
        ast = parser.parse(dsl)
        self.assertEqual(len(ast.functions), 1)
        fn = ast.functions[0]
        self.assertEqual(fn['name'], 'DoubleIt')
        self.assertEqual(fn['parameters'], ['Value'])
        self.assertEqual(len(fn['returns']), 1)
        self.assertEqual(ast.cyclomatic_complexity, 1)

    def test_parse_event_with_branching_and_calls(self):
        dsl = """
        (event OnHit (Damage)
          (bind isDead (<= (Variables|Health|GetHealth) Damage))
          (if isDead
            (Character|PlayDeathAnimation)
            (else
              (Character|PlayFlinchAnimation))))
        """
        parser = BlueprintParser()
        ast = parser.parse(dsl)

        self.assertEqual(len(ast.events), 1)
        ev = ast.events[0]
        self.assertEqual(ev['name'], 'OnHit')
        self.assertEqual(ev['parameters'], ['Damage'])
        self.assertIn('Character|PlayDeathAnimation', ev['calls'])
        self.assertIn('Character|PlayFlinchAnimation', ev['calls'])
        self.assertIn('Health', ev['variables_read'])
        self.assertIn('isDead', ev['variables_written'])
        # if branch increases complexity
        self.assertEqual(ast.branch_count, 1)
        self.assertEqual(ast.cyclomatic_complexity, 2)

    def test_parse_real_ui_ingame_dsl(self):
        # Exact snippet observed from UnrealCodexTest
        real_dsl = """
        (event Custom|ToggleDetails (Visible)
          (bind _detailsdemo (Variables|Animations|GetDetailsDemo))
          (if Visible
            (UserInterface|Animation|PlayAnimation _detailsdemo 0.000000 0 "Forward" 1.000000 true)
            (Widget|SetVisibility (Variables|UI_InGame|GetDetails))
            (else
              (UserInterface|Animation|StopAnimation _detailsdemo)
              (Widget|SetVisibility (Variables|UI_InGame|GetDetails) "Collapsed"))))
        """
        parser = BlueprintParser()
        ast = parser.parse(real_dsl)

        self.assertEqual(len(ast.events), 1)
        ev = ast.events[0]
        self.assertEqual(ev['name'], 'Custom|ToggleDetails')
        self.assertEqual(ev['parameters'], ['Visible'])
        self.assertIn('UserInterface|Animation|PlayAnimation', ev['calls'])
        self.assertIn('Widget|SetVisibility', ev['calls'])
        self.assertIn('UserInterface|Animation|StopAnimation', ev['calls'])
        self.assertIn('_detailsdemo', ev['variables_written'])

    def test_format_ast_markdown(self):
        dsl = """
        (event BeginPlay ()
          (Development|PrintString "Game Started"))
        """
        summary = summarize_dsl(dsl)
        md = format_ast_markdown(summary)
        self.assertIn("BeginPlay", md)
        self.assertIn("PrintString", md)
        self.assertIn("Complexity Score", md)


if __name__ == '__main__':
    unittest.main()

