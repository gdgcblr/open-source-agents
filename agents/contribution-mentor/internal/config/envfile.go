package config

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
)

func LoadDotEnv(filename string) (resultErr error) {
	file, err := os.Open(filename)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("open environment file %q: %w", filename, err)
	}
	defer func() {
		if err := file.Close(); err != nil {
			resultErr = errors.Join(resultErr, fmt.Errorf("close environment file %q: %w", filename, err))
		}
	}()

	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1024), 1024*1024)
	lineNumber := 0
	for scanner.Scan() {
		lineNumber++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimSpace(strings.TrimPrefix(line, "export "))
		key, value, found := strings.Cut(line, "=")
		if !found {
			return fmt.Errorf("parse environment file %q at line %d: expected KEY=VALUE", filename, lineNumber)
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if !isEnvironmentKey(key) {
			return fmt.Errorf("parse environment file %q at line %d: invalid key", filename, lineNumber)
		}
		if strings.HasPrefix(value, "\"") {
			unquoted, err := strconv.Unquote(value)
			if err != nil {
				return fmt.Errorf("parse environment file %q at line %d: invalid quoted value", filename, lineNumber)
			}
			value = unquoted
		} else if strings.HasPrefix(value, "'") {
			if len(value) < 2 || !strings.HasSuffix(value, "'") {
				return fmt.Errorf("parse environment file %q at line %d: invalid quoted value", filename, lineNumber)
			}
			value = value[1 : len(value)-1]
		} else if commentIndex := strings.Index(value, " #"); commentIndex >= 0 {
			value = strings.TrimSpace(value[:commentIndex])
		}
		if _, exists := os.LookupEnv(key); exists {
			continue
		}
		if err := os.Setenv(key, value); err != nil {
			return fmt.Errorf("set environment variable from %q line %d: %w", filename, lineNumber, err)
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("read environment file %q: %w", filename, err)
	}
	return nil
}

func isEnvironmentKey(key string) bool {
	if key == "" {
		return false
	}
	for index, character := range key {
		if (character >= 'A' && character <= 'Z') ||
			(character >= 'a' && character <= 'z') ||
			character == '_' || (index > 0 && character >= '0' && character <= '9') {
			continue
		}
		return false
	}
	return true
}
