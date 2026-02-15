import bcrypt from "bcryptjs";
import * as jwt from "jsonwebtoken";

const JWT_SECRET = process.env.JWT_SECRET || "dev_secret_change_me";

export async function hashPassword(password: string) {
  const salt = await bcrypt.genSalt(10);
  return bcrypt.hash(password, salt);
}

export async function comparePassword(password: string, hash: string) {
  return bcrypt.compare(password, hash);
}

export function createJwt(payload: Record<string, unknown>, expiresIn = "7d") {
  return jwt.sign(payload, JWT_SECRET as jwt.Secret, { expiresIn } as jwt.SignOptions);
}

export function verifyJwt(token: string): Record<string, unknown> | null {
  try {
    return jwt.verify(token, JWT_SECRET as jwt.Secret) as Record<string, unknown>;
  } catch (e) {
    return null;
  }
}
