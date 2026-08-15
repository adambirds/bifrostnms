package main

import (
	"fmt"
	"runtime/debug"
)

func main() {
	version := "dev"
	if info, ok := debug.ReadBuildInfo(); ok && info.Main.Version != "" {
		version = info.Main.Version
	}
	fmt.Printf("BifrostNMS Agent %s\n", version)
}
