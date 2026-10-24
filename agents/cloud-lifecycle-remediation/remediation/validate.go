package remediation

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// RunTerraformValidate runs terraform fmt -check and terraform validate in WorkingDir.
func RunTerraformValidate(ctx context.Context, args RunTerraformValidateArgs) (RunTerraformValidateResult, error) {
	if args.WorkingDir == "" {
		return RunTerraformValidateResult{
			Output:  "working_dir is required",
			Success: false,
		}, nil
	}

	if _, err := exec.LookPath("terraform"); err != nil {
		return RunTerraformValidateResult{
			Success: false,
			Output:  "terraform binary not found in PATH; install Terraform 1.5+ to validate configurations",
		}, nil
	}

	var buf bytes.Buffer
	run := func(name string, cmdArgs ...string) error {
		cmd := exec.CommandContext(ctx, name, cmdArgs...)
		cmd.Dir = args.WorkingDir
		cmd.Env = os.Environ()
		out, err := cmd.CombinedOutput()
		buf.WriteString(fmt.Sprintf("$ %s %s\n", name, strings.Join(cmdArgs, " ")))
		buf.Write(out)
		if len(out) > 0 && out[len(out)-1] != '\n' {
			buf.WriteByte('\n')
		}
		return err
	}

	// Format in-place so validate sees normalized HCL.
	if err := run("terraform", "fmt", "-recursive"); err != nil {
		return RunTerraformValidateResult{Success: false, Output: buf.String()}, nil
	}
	if err := run("terraform", "init", "-backend=false", "-input=false"); err != nil {
		return RunTerraformValidateResult{Success: false, Output: buf.String()}, nil
	}
	if err := run("terraform", "validate"); err != nil {
		return RunTerraformValidateResult{Success: false, Output: buf.String()}, nil
	}

	return RunTerraformValidateResult{Success: true, Output: buf.String()}, nil
}
