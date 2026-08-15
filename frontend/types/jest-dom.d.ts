// jest.setup.js loads @testing-library/jest-dom at runtime; this pulls in its
// matcher types so tests don't each have to import it just to satisfy tsc.
import "@testing-library/jest-dom";
