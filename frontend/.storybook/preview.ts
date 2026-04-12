import type { Preview } from '@storybook/react-vite'

import '../src/index.css'

const preview: Preview = {
  parameters: {
    layout: 'centered',
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'command-center',
      values: [
        { name: 'command-center', value: '#08111f' },
        { name: 'paper-light', value: '#f4f8fc' },
      ],
    },
    a11y: {
      test: 'error',
    },
    options: {
      storySort: {
        order: ['Overview', 'Primitives'],
      },
    },
  },
}

export default preview
