# Generated from Fml.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .FmlParser import FmlParser
else:
    from FmlParser import FmlParser

# This class defines a complete listener for a parse tree produced by FmlParser.
class FmlListener(ParseTreeListener):

    # Enter a parse tree produced by FmlParser#program.
    def enterProgram(self, ctx:FmlParser.ProgramContext):
        pass

    # Exit a parse tree produced by FmlParser#program.
    def exitProgram(self, ctx:FmlParser.ProgramContext):
        pass


    # Enter a parse tree produced by FmlParser#group.
    def enterGroup(self, ctx:FmlParser.GroupContext):
        pass

    # Exit a parse tree produced by FmlParser#group.
    def exitGroup(self, ctx:FmlParser.GroupContext):
        pass


    # Enter a parse tree produced by FmlParser#params.
    def enterParams(self, ctx:FmlParser.ParamsContext):
        pass

    # Exit a parse tree produced by FmlParser#params.
    def exitParams(self, ctx:FmlParser.ParamsContext):
        pass


    # Enter a parse tree produced by FmlParser#param.
    def enterParam(self, ctx:FmlParser.ParamContext):
        pass

    # Exit a parse tree produced by FmlParser#param.
    def exitParam(self, ctx:FmlParser.ParamContext):
        pass


    # Enter a parse tree produced by FmlParser#extendsClause.
    def enterExtendsClause(self, ctx:FmlParser.ExtendsClauseContext):
        pass

    # Exit a parse tree produced by FmlParser#extendsClause.
    def exitExtendsClause(self, ctx:FmlParser.ExtendsClauseContext):
        pass


    # Enter a parse tree produced by FmlParser#typeMode.
    def enterTypeMode(self, ctx:FmlParser.TypeModeContext):
        pass

    # Exit a parse tree produced by FmlParser#typeMode.
    def exitTypeMode(self, ctx:FmlParser.TypeModeContext):
        pass


    # Enter a parse tree produced by FmlParser#typeModeBody.
    def enterTypeModeBody(self, ctx:FmlParser.TypeModeBodyContext):
        pass

    # Exit a parse tree produced by FmlParser#typeModeBody.
    def exitTypeModeBody(self, ctx:FmlParser.TypeModeBodyContext):
        pass


    # Enter a parse tree produced by FmlParser#body.
    def enterBody(self, ctx:FmlParser.BodyContext):
        pass

    # Exit a parse tree produced by FmlParser#body.
    def exitBody(self, ctx:FmlParser.BodyContext):
        pass


    # Enter a parse tree produced by FmlParser#element.
    def enterElement(self, ctx:FmlParser.ElementContext):
        pass

    # Exit a parse tree produced by FmlParser#element.
    def exitElement(self, ctx:FmlParser.ElementContext):
        pass


    # Enter a parse tree produced by FmlParser#thenClause.
    def enterThenClause(self, ctx:FmlParser.ThenClauseContext):
        pass

    # Exit a parse tree produced by FmlParser#thenClause.
    def exitThenClause(self, ctx:FmlParser.ThenClauseContext):
        pass


    # Enter a parse tree produced by FmlParser#block.
    def enterBlock(self, ctx:FmlParser.BlockContext):
        pass

    # Exit a parse tree produced by FmlParser#block.
    def exitBlock(self, ctx:FmlParser.BlockContext):
        pass


    # Enter a parse tree produced by FmlParser#invocation.
    def enterInvocation(self, ctx:FmlParser.InvocationContext):
        pass

    # Exit a parse tree produced by FmlParser#invocation.
    def exitInvocation(self, ctx:FmlParser.InvocationContext):
        pass


    # Enter a parse tree produced by FmlParser#anyToken.
    def enterAnyToken(self, ctx:FmlParser.AnyTokenContext):
        pass

    # Exit a parse tree produced by FmlParser#anyToken.
    def exitAnyToken(self, ctx:FmlParser.AnyTokenContext):
        pass



del FmlParser