"""EmailGateway - sends generated activities as PDF to therapists."""


class EmailGateway:
    def send(self, pdf_bytes: bytes, recipient_email: str) -> bool:
        # TODO: integrate transactional email provider
        print(f"[email] would send {len(pdf_bytes)} bytes to {recipient_email}")
        return True
