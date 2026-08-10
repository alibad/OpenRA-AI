import { createRemoteJWKSet, jwtVerify } from "jose";

const firebaseProjectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
const firebaseKeys = createRemoteJWKSet(
  new URL("https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"),
);

export type FirebaseIdentity = {
  uid: string;
  email: string | null;
  name: string | null;
};

export async function verifyFirebaseIdentity(request: Request): Promise<FirebaseIdentity | null> {
  if (!firebaseProjectId) return null;
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) return null;
  const token = authorization.slice("Bearer ".length).trim();
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, firebaseKeys, {
      audience: firebaseProjectId,
      issuer: `https://securetoken.google.com/${firebaseProjectId}`,
    });
    if (typeof payload.sub !== "string" || !payload.sub) return null;
    return {
      uid: payload.sub,
      email: typeof payload.email === "string" && payload.email ? payload.email : null,
      name: typeof payload.name === "string" && payload.name ? payload.name : null,
    };
  } catch {
    return null;
  }
}

export async function verifyFirebaseRequest(request: Request) {
  return (await verifyFirebaseIdentity(request))?.uid ?? null;
}
