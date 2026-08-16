package main

import (
	"testing"

	"github.com/adambirds/bifrostnms/agent/protocol"
)

func TestIssuedCredentialSecret(t *testing.T) {
	t.Parallel()

	response := protocol.EnrolmentResponse{
		CredentialID: "123e4567-e89b-12d3-a456-426614174000",
		Credential:   "123e4567-e89b-12d3-a456-426614174000.secret-value",
	}

	secret, err := issuedCredentialSecret(response)
	if err != nil {
		t.Fatalf("issuedCredentialSecret returned error: %v", err)
	}
	if secret != "secret-value" {
		t.Fatalf("issuedCredentialSecret returned %q, want %q", secret, "secret-value")
	}
}

func TestIssuedCredentialSecretRejectsMismatchedIdentifier(t *testing.T) {
	t.Parallel()

	response := protocol.EnrolmentResponse{
		CredentialID: "123e4567-e89b-12d3-a456-426614174000",
		Credential:   "00000000-0000-0000-0000-000000000000.secret-value",
	}

	if _, err := issuedCredentialSecret(response); err == nil {
		t.Fatal("issuedCredentialSecret accepted a mismatched credential identifier")
	}
}

func TestIssuedCredentialSecretRejectsMalformedCredential(t *testing.T) {
	t.Parallel()

	response := protocol.EnrolmentResponse{
		CredentialID: "123e4567-e89b-12d3-a456-426614174000",
		Credential:   "not-a-complete-credential",
	}

	if _, err := issuedCredentialSecret(response); err == nil {
		t.Fatal("issuedCredentialSecret accepted a malformed credential")
	}
}
