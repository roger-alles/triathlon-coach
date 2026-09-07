// Reanimated 4 i Worklets necessiten runtime natiu; a Jest fem servir els mocks oficials.
// https://docs.swmansion.com/react-native-worklets/docs/guides/testing
jest.mock('react-native-worklets', () => require('react-native-worklets/src/mock'));
jest.mock('react-native-reanimated', () => require('react-native-reanimated/mock'));
