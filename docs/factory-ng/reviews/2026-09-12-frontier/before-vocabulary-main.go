// Extract the public effect dispatcher and registry using Go syntax, not comments.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strconv"
)

func literal(e ast.Expr) string {
	if s, ok := e.(*ast.BasicLit); ok && s.Kind == token.STRING {
		v, _ := strconv.Unquote(s.Value)
		return v
	}
	return ""
}

func main() {
	var sources map[string]string
	if err := json.NewDecoder(os.Stdin).Decode(&sources); err != nil {
		panic(err)
	}
	dispatch, registered := map[string]bool{}, map[string]bool{}
	for name, src := range sources {
		f, err := parser.ParseFile(token.NewFileSet(), name, src, 0)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		ast.Inspect(f, func(n ast.Node) bool {
			switch x := n.(type) {
			case *ast.FuncDecl:
				if name == "dispatch" || name == "base" {
					if x.Name.Name != "ExecuteAbilityEffect" {
						return false
					}
				} else if x.Name.Name != "init" {
					return false
				}
			case *ast.BinaryExpr:
				if (name == "dispatch" || name == "base") && x.Op == token.EQL {
					if id, ok := x.X.(*ast.Ident); ok && id.Name == "effect" {
						if v := literal(x.Y); v != "" {
							dispatch[v] = true
						}
					}
					if id, ok := x.Y.(*ast.Ident); ok && id.Name == "effect" {
						if v := literal(x.X); v != "" {
							dispatch[v] = true
						}
					}
				}
			case *ast.SwitchStmt:
				if name != "dispatch" && name != "base" {
					break
				}
				if tag, ok := x.Tag.(*ast.Ident); ok && tag.Name == "effect" {
					for _, statement := range x.Body.List {
						for _, e := range statement.(*ast.CaseClause).List {
							if v := literal(e); v != "" {
								dispatch[v] = true
							}
						}
					}
					return false
				}
			case *ast.CallExpr:
				if fn, ok := x.Fun.(*ast.Ident); ok && fn.Name == "regEffect" && len(x.Args) > 0 {
					if v := literal(x.Args[0]); v != "" {
						registered[v] = true
					}
				}
			case *ast.ValueSpec:
				for i, id := range x.Names {
					if id.Name != "V2EffectRegistry" || i >= len(x.Values) {
						continue
					}
					if m, ok := x.Values[i].(*ast.CompositeLit); ok {
						for _, e := range m.Elts {
							if kv, ok := e.(*ast.KeyValueExpr); ok {
								if v := literal(kv.Key); v != "" {
									registered[v] = true
								}
							}
						}
					}
				}
			case *ast.AssignStmt:
				for _, lhs := range x.Lhs {
					if idx, ok := lhs.(*ast.IndexExpr); ok {
						if id, ok := idx.X.(*ast.Ident); ok && id.Name == "V2EffectRegistry" {
							if v := literal(idx.Index); v != "" {
								registered[v] = true
							}
						}
					}
				}
			}
			return true
		})
	}
	json.NewEncoder(os.Stdout).Encode(map[string]interface{}{"dispatch": dispatch, "registered": registered})
}
