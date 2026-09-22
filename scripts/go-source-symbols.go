// Source locations from Go's parser, never from the first textual mention.
package main

import (
	"bytes"
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/printer"
	"go/token"
	"os"
	"strconv"
)

type Symbol struct {
	Name      string `json:"name"`
	Receiver  string `json:"receiver"`
	Package   string `json:"package"`
	Kind      string `json:"kind"`
	Path      string `json:"path"`
	Start     int    `json:"start"`
	End       int    `json:"end"`
	Signature string `json:"signature"`
	Doc       string `json:"doc"`
}

func main() {
	var paths []string
	if err := json.NewDecoder(os.Stdin).Decode(&paths); err != nil {
		panic(err)
	}
	rows := []Symbol{}
	for _, path := range paths {
		fs := token.NewFileSet()
		f, err := parser.ParseFile(fs, path, nil, parser.ParseComments)
		if err != nil {
			continue
		}
		for _, decl := range f.Decls {
			switch d := decl.(type) {
			case *ast.FuncDecl:
				receiver := ""
				if d.Recv != nil && len(d.Recv.List) > 0 {
					x := d.Recv.List[0].Type
					if p, ok := x.(*ast.StarExpr); ok {
						x = p.X
					}
					var b bytes.Buffer
					printer.Fprint(&b, fs, x)
					receiver = b.String()
				}
				var b bytes.Buffer
				copy := *d
				copy.Body = nil
				copy.Doc = nil
				printer.Fprint(&b, fs, &copy)
				rows = append(rows, Symbol{d.Name.Name, receiver, f.Name.Name, "function", path, fs.Position(d.Pos()).Line, fs.Position(d.End()).Line, b.String(), d.Doc.Text()})
				if d.Body != nil {
					ast.Inspect(d.Body, func(n ast.Node) bool {
						c, ok := n.(*ast.CaseClause)
						if !ok {
							return true
						}
						for _, expr := range c.List {
							lit, ok := expr.(*ast.BasicLit)
							if !ok || lit.Kind != token.STRING {
								continue
							}
							name, err := strconv.Unquote(lit.Value)
							if err != nil {
								continue
							}
							rows = append(rows, Symbol{name, receiver, f.Name.Name, "case", path, fs.Position(c.Pos()).Line, fs.Position(c.End()).Line, d.Name.Name + "#case:" + name, ""})
						}
						return true
					})
				}
			case *ast.GenDecl:
				if d.Tok != token.TYPE {
					continue
				}
				for _, spec := range d.Specs {
					t := spec.(*ast.TypeSpec)
					rows = append(rows, Symbol{t.Name.Name, "", f.Name.Name, "type", path, fs.Position(t.Pos()).Line, fs.Position(t.End()).Line, "type " + t.Name.Name, d.Doc.Text()})
				}
			}
		}
	}
	json.NewEncoder(os.Stdout).Encode(rows)
}
