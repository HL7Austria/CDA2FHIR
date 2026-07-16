/*
 * Fml.g4 - A tolerant ANTLR4 grammar for the FHIR Mapping Language (.map / FML).
 *
 * This grammar is intentionally *structural*, not a full FML/FHIRPath grammar.
 * It parses precisely the constructs needed to build a group call/extends graph:
 *
 *   - group headers:      group NAME(params) [extends PARENT] [<<typeMode>>] { ... }
 *   - parameters:         source|target NAME [: TYPE]
 *   - dependent calls:    then NAME(args)           (how one group calls another)
 *   - inline then blocks: then { ... }
 *
 * Everything else (the `map` line, `uses`, `imports`, inline `conceptmap { }`
 * blocks, and all FHIRPath inside rule bodies) is consumed as opaque filler
 * tokens. This keeps the grammar robust against arbitrary FHIRPath expressions
 * while still deterministically recovering the modularization structure.
 *
 * Regenerate the Python parser with (ANTLR runtime must match, currently 4.13.2):
 *   java -jar antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor Fml.g4
 */
grammar Fml;

// ---------------------------------------------------------------------------
// Parser rules
// ---------------------------------------------------------------------------

// A whole .map file: a stream of top-level groups interleaved with any other
// top-level content (map decl, uses, imports, conceptmaps), which we skip over.
program : (group | element)* EOF ;

// group NAME(params) [extends PARENT] [<<typeMode>>] { body }
group
    : GROUP name=ID params extendsClause? typeMode? body
    ;

params
    : LPAREN (param (COMMA param)*)? RPAREN
    ;

// source foo : Bar   |   target foo   |   source foo
param
    : direction=(SOURCE | TARGET) pname=ID (COLON ptype=ID)?
    ;

extendsClause
    : EXTENDS parent=ID
    ;

// <<types>> | <<type+types>> | <<any>>
typeMode
    : LTLT typeModeBody GTGT
    ;

typeModeBody
    : ID (PLUS ID)*
    ;

body
    : LBRACE element* RBRACE
    ;

// A single element inside a group body (or at top level).
//   - THEN starts a dependent: either a nested block or a group invocation list
//   - balanced { } and ( ) groups are recursed into (to stay in sync)
//   - anything else is opaque filler
element
    : THEN thenClause
    | LBRACE element* RBRACE
    | LPAREN element* RPAREN
    | anyToken
    ;

thenClause
    : block                                    // then { ... }
    | invocation (COMMA invocation)*           // then Group(args) [, Group(args)]
    ;

block
    : LBRACE element* RBRACE
    ;

// Group.other(...) invocation. We only care about the callee name; args are
// consumed as balanced filler.
invocation
    : callee=ID LPAREN element* RPAREN
    ;

// Any token that is not a structural delimiter handled by the rules above.
anyToken
    : ~(LBRACE | RBRACE | LPAREN | RPAREN | THEN)
    ;

// ---------------------------------------------------------------------------
// Lexer rules
// ---------------------------------------------------------------------------

// Keywords (declared before ID so they win the longest-match tie-break).
GROUP   : 'group' ;
EXTENDS : 'extends' ;
THEN    : 'then' ;
SOURCE  : 'source' ;
TARGET  : 'target' ;

LBRACE  : '{' ;
RBRACE  : '}' ;
LPAREN  : '(' ;
RPAREN  : ')' ;
LTLT    : '<<' ;
GTGT    : '>>' ;
COLON   : ':' ;
COMMA   : ',' ;
PLUS    : '+' ;

ID      : [A-Za-z_] [A-Za-z0-9_]* ;

NUMBER  : [0-9]+ ('.' [0-9]+)? ;

// String literals: single, double and backtick delimited, with backslash escapes.
STRING
    : '\'' (ESC | ~['\\])* '\''
    | '"'  (ESC | ~["\\])* '"'
    | '`'  ~[`]*            '`'
    ;

fragment ESC : '\\' . ;

LINE_COMMENT  : '//' ~[\r\n]*            -> skip ;
BLOCK_COMMENT : '/*' .*? '*/'            -> skip ;
WS            : [ \t\r\n ]+         -> skip ;

// Catch-all: any other single character (=, ., ;, -, >, <, *, /, %, $, [, ], etc.)
// keeps the lexer from ever failing on FHIRPath punctuation.
ANY : . ;
