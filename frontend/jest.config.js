const nextJest = require("next/jest");

const createJestConfig = nextJest({ dir: "./" });

module.exports = createJestConfig({
  testEnvironment: "jest-environment-jsdom",
  // Was `setupFilesAfterFramework`, which Jest silently ignores — jest.setup.js
  // never loaded, and the existing tests only passed because each one imported
  // @testing-library/jest-dom itself.
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  testMatch: ["**/__tests__/**/*.test.{ts,tsx,js,jsx}"],
});
