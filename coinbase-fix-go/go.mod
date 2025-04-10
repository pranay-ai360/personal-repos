module com.fix // Or your module name

go 1.21 // Or 1.20 if that works

require (
	github.com/google/uuid v1.6.0 // Or let tidy manage
	github.com/quickfixgo/quickfix v0.9.6 // Target this version
)

// Let 'go mod tidy' manage indirects

// Leave the indirect require block as is, go mod tidy will adjust it
require (
	github.com/pkg/errors v0.9.1 // indirect
	github.com/shopspring/decimal v1.4.0 // indirect
	golang.org/x/net v0.24.0 // indirect
)

require (
	github.com/quickfixgo/enum v0.1.0
	github.com/quickfixgo/field v0.1.0
	github.com/quickfixgo/fix50sp2 v0.1.0
	github.com/quickfixgo/fixt11 v0.1.0
	github.com/quickfixgo/tag v0.1.0
)

require github.com/pires/go-proxyproto v0.7.0 // indirect
