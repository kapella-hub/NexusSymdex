"""Tests for language-specific parsing."""

import pytest
from nexus_symdex.parser import parse_file


JAVASCRIPT_SOURCE = '''
/** Greet a user. */
function greet(name) {
    return `Hello, ${name}!`;
}

class Calculator {
    /** Add two numbers. */
    add(a, b) {
        return a + b;
    }
}

const MAX_RETRY = 5;
'''


def test_parse_javascript():
    """Test JavaScript parsing."""
    symbols = parse_file(JAVASCRIPT_SOURCE, "app.js", "javascript")
    
    # Should have function, class, method, constant
    func = next((s for s in symbols if s.name == "greet"), None)
    assert func is not None
    assert func.kind == "function"
    assert "Greet a user" in func.docstring
    
    cls = next((s for s in symbols if s.name == "Calculator"), None)
    assert cls is not None
    assert cls.kind == "class"
    
    method = next((s for s in symbols if s.name == "add"), None)
    assert method is not None
    assert method.kind == "method"


TYPESCRIPT_SOURCE = '''
interface User {
    name: string;
}

/** Get user by ID. */
function getUser(id: number): User {
    return { name: "Test" };
}

class UserService {
    private users: User[] = [];
    
    @cache()
    findById(id: number): User | undefined {
        return this.users.find(u => u.id === id);
    }
}

type ID = string | number;
'''


def test_parse_typescript():
    """Test TypeScript parsing."""
    symbols = parse_file(TYPESCRIPT_SOURCE, "service.ts", "typescript")
    
    # Should have interface, function, class, method, type alias
    func = next((s for s in symbols if s.name == "getUser"), None)
    assert func is not None
    assert func.kind == "function"
    
    interface = next((s for s in symbols if s.name == "User"), None)
    assert interface is not None
    assert interface.kind == "type"


GO_SOURCE = '''
package main

import "fmt"

// Person represents a person.
type Person struct {
    Name string
}

// Greet prints a greeting.
func (p *Person) Greet() {
    fmt.Println("Hello, " + p.Name)
}

// Add adds two numbers.
func Add(a, b int) int {
    return a + b
}

const MaxCount = 100
'''


def test_parse_go():
    """Test Go parsing."""
    symbols = parse_file(GO_SOURCE, "main.go", "go")
    
    # Should have type, method, function, constant
    person = next((s for s in symbols if s.name == "Person"), None)
    assert person is not None
    assert person.kind == "type"
    
    greet = next((s for s in symbols if s.name == "Greet"), None)
    assert greet is not None
    assert greet.kind == "method"


RUST_SOURCE = '''
/// A user in the system.
pub struct User {
    name: String,
}

impl User {
    /// Create a new user.
    pub fn new(name: &str) -> Self {
        Self { name: name.to_string() }
    }
    
    /// Get the user's name.
    pub fn name(&self) -> &str {
        &self.name
    }
}

pub const MAX_USERS: usize = 1000;
'''


def test_parse_rust():
    """Test Rust parsing."""
    symbols = parse_file(RUST_SOURCE, "user.rs", "rust")
    
    # Should have struct, impl, methods, constant
    user = next((s for s in symbols if s.name == "User"), None)
    assert user is not None
    assert user.kind == "type"


JAVA_SOURCE = '''
/**
 * A simple calculator.
 */
public class Calculator {
    public static final int MAX_VALUE = 100;
    
    /**
     * Add two numbers.
     */
    public int add(int a, int b) {
        return a + b;
    }
}

interface Operable {
    int operate(int a, int b);
}
'''


def test_parse_java():
    """Test Java parsing."""
    symbols = parse_file(JAVA_SOURCE, "Calculator.java", "java")

    # Should have class, method, interface
    calc = next((s for s in symbols if s.name == "Calculator"), None)
    assert calc is not None
    assert calc.kind == "class"

    add = next((s for s in symbols if s.name == "add"), None)
    assert add is not None
    assert add.kind == "method"


PHP_SOURCE = '''<?php

const MAX_RETRIES = 3;

/**
 * Authenticate a user token.
 */
function authenticate(string $token): bool
{
    return strlen($token) > 0;
}

/**
 * Manages user operations.
 */
class UserService
{
    /**
     * Get a user by ID.
     */
    public function getUser(int $userId): array
    {
        return ['id' => $userId];
    }
}

interface Authenticatable
{
    public function authenticate(string $token): bool;
}

trait Timestampable
{
    public function getCreatedAt(): string
    {
        return date(\'Y-m-d\');
    }
}

enum Status
{
    case Active;
    case Inactive;
}
'''


def test_parse_php():
    """Test PHP parsing."""
    symbols = parse_file(PHP_SOURCE, "service.php", "php")

    func = next((s for s in symbols if s.name == "authenticate"), None)
    assert func is not None
    assert func.kind == "function"
    assert "Authenticate a user token" in func.docstring

    cls = next((s for s in symbols if s.name == "UserService"), None)
    assert cls is not None
    assert cls.kind == "class"

    method = next((s for s in symbols if s.name == "getUser"), None)
    assert method is not None
    assert method.kind == "method"
    assert "Get a user by ID" in method.docstring

    interface = next((s for s in symbols if s.name == "Authenticatable"), None)
    assert interface is not None
    assert interface.kind == "type"

    trait = next((s for s in symbols if s.name == "Timestampable"), None)
    assert trait is not None
    assert trait.kind == "type"

    enum = next((s for s in symbols if s.name == "Status"), None)
    assert enum is not None
    assert enum.kind == "type"


# ---- Assigned function extraction tests ----

JS_ASSIGNED_FUNCTIONS = '''
/** Set status code. */
res.status = function status(code) {
  this.statusCode = code;
  return this;
};

const handler = (req, res) => {
  res.json({ ok: true });
};

var render = function render(view, opts) {
  return view;
};

exports.createApp = function createApp() {
  return {};
};

module.exports.init = function init(config) {
  return config;
};

Foo.prototype.bar = function bar(x) {
  return x;
};

/** Both names point to the same function. */
res.contentType =
res.type = function contentType(type) {
  return type;
};
'''


def test_parse_js_property_assignments():
    """Test that property assignment functions are captured."""
    symbols = parse_file(JS_ASSIGNED_FUNCTIONS, "test.js", "javascript")

    status = next((s for s in symbols if s.name == "status"), None)
    assert status is not None
    assert status.kind == "method"
    assert status.qualified_name == "res.status"
    assert "Set status code" in status.docstring


def test_parse_js_variable_arrow_function():
    """Test that arrow functions in variable declarations are captured."""
    symbols = parse_file(JS_ASSIGNED_FUNCTIONS, "test.js", "javascript")

    handler = next((s for s in symbols if s.name == "handler"), None)
    assert handler is not None
    assert handler.kind == "function"
    assert "handler" in handler.signature


def test_parse_js_variable_function_expression():
    """Test that function expressions in variable declarations are captured."""
    symbols = parse_file(JS_ASSIGNED_FUNCTIONS, "test.js", "javascript")

    render = next((s for s in symbols if s.name == "render"), None)
    assert render is not None
    assert render.kind == "function"


def test_parse_js_commonjs_exports():
    """Test that CommonJS export functions are captured."""
    symbols = parse_file(JS_ASSIGNED_FUNCTIONS, "test.js", "javascript")

    create = next((s for s in symbols if s.name == "createApp"), None)
    assert create is not None
    assert create.kind == "function"

    init = next((s for s in symbols if s.name == "init"), None)
    assert init is not None
    assert init.kind == "function"


def test_parse_js_prototype_assignment():
    """Test that prototype method assignments are captured."""
    symbols = parse_file(JS_ASSIGNED_FUNCTIONS, "test.js", "javascript")

    bar = next((s for s in symbols if s.name == "bar"), None)
    assert bar is not None
    assert bar.kind == "method"
    assert bar.qualified_name == "Foo.bar"


def test_parse_js_chained_alias_assignment():
    """Test chained assignments like res.contentType = res.type = function()."""
    symbols = parse_file(JS_ASSIGNED_FUNCTIONS, "test.js", "javascript")

    # Primary name (innermost assignment target)
    typ = next((s for s in symbols if s.name == "type"), None)
    assert typ is not None
    assert typ.kind == "method"
    assert "Both names" in typ.docstring

    # Alias (outer assignment target)
    ct = next((s for s in symbols if s.name == "contentType"), None)
    assert ct is not None
    assert "Alias for" in ct.docstring

