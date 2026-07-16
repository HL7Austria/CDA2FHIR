# Generated from Fml.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .FmlParser import FmlParser
else:
    from FmlParser import FmlParser

# This class defines a complete generic visitor for a parse tree produced by FmlParser.

class FmlVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by FmlParser#program.
    def visitProgram(self, ctx:FmlParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#group.
    def visitGroup(self, ctx:FmlParser.GroupContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#params.
    def visitParams(self, ctx:FmlParser.ParamsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#param.
    def visitParam(self, ctx:FmlParser.ParamContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#extendsClause.
    def visitExtendsClause(self, ctx:FmlParser.ExtendsClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#typeMode.
    def visitTypeMode(self, ctx:FmlParser.TypeModeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#typeModeBody.
    def visitTypeModeBody(self, ctx:FmlParser.TypeModeBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#body.
    def visitBody(self, ctx:FmlParser.BodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#element.
    def visitElement(self, ctx:FmlParser.ElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#thenClause.
    def visitThenClause(self, ctx:FmlParser.ThenClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#block.
    def visitBlock(self, ctx:FmlParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#invocation.
    def visitInvocation(self, ctx:FmlParser.InvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FmlParser#anyToken.
    def visitAnyToken(self, ctx:FmlParser.AnyTokenContext):
        return self.visitChildren(ctx)



del FmlParser