import { z } from 'zod'

export function tool(name, description, shape, handler) {
  const schema = z.object(shape)
  return { name, description, parameters: z.toJSONSchema(schema, { io: 'input', unrepresentable: 'any' }),
    call: (args, signal) => handler(schema.parse(args), signal) }
}

export function createToolServer(server) {
  return server
}
