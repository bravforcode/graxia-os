import winston from 'winston';

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  defaultMeta: { service: 'bravos-service' },
  transports: [
    new winston.transports.Console(),
  ],
});

/**
 * Log a message with an optional trace_id
 * @param level - The log level ('info', 'error', 'warn', etc.)
 * @param message - The message to log
 * @param traceId - Optional trace ID for tracking across services
 * @param meta - Additional metadata
 */
export const log = (level: string, message: string, traceId?: string, meta: object = {}) => {
  logger.log(level, message, { trace_id: traceId, ...meta });
};

export default logger;
