// Voice search and address matching.   node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const S = require("../search-text.js");

test("spoken numbers become one run of digits (SAP IDs, phone numbers)", () => {
  assert.equal(S.spokenToQuery("123 456 789"), "123456789");
  assert.equal(S.spokenToQuery("123-456-789."), "123456789");
  assert.equal(S.spokenToQuery("SAP 123 456 789"), "123456789");
  assert.equal(S.spokenToQuery("S A P 1 2 3 4 5 6 7 8 9"), "123456789");
  assert.equal(S.spokenToQuery("(530) 555-1234"), "5305551234");
  assert.equal(S.spokenToQuery("phone number 530 555 1234"), "5305551234");
  assert.equal(S.spokenToQuery("five three oh five five five"), "530555");
  assert.equal(S.spokenToQuery("Five, three, zero."), "530");
});

test("words stay words, minus the punctuation the engine adds", () => {
  assert.equal(S.spokenToQuery("Main Street."), "Main Street");
  assert.equal(S.spokenToQuery("  John Smith?"), "John Smith");
  assert.equal(S.spokenToQuery("123 Main Street"), "123 Main Street");
  assert.equal(S.spokenToQuery("one way"), "one way");          // not a number: "way" isn't a digit
  assert.equal(S.spokenToQuery("Oh"), "Oh");                       // a lone "oh" isn't a number
  assert.equal(S.spokenToQuery("SAP"), "SAP");
  assert.equal(S.spokenToQuery(""), "");
});

test("street types match however they are written", () => {
  assert.ok(S.wordsMatch("123 MAIN ST, Redding, CA", "123 main street"));
  assert.ok(S.wordsMatch("123 Main Street, Redding", "123 main st"));
  assert.ok(S.wordsMatch("4500 Churn Creek Rd.", "churn creek road"));
  assert.ok(S.wordsMatch("88 N. Market St", "north market street"));
  assert.ok(S.wordsMatch("10 1st Ave", "first avenue"));
  assert.ok(!S.wordsMatch("123 Main St", "main road"));
});

test("whole words only, so short forms don't match inside other words", () => {
  assert.ok(S.wordsMatch("200 W Cypress Ave", "west cypress"));
  assert.ok(!S.wordsMatch("200 Walnut Ave", "west"));
  assert.ok(!S.wordsMatch("Stanford Hills Trail", "street"));
  assert.ok(!S.wordsMatch("anything", ""));
});
