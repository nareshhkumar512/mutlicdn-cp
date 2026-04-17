import logging

class AkamaiAdapter:
    def __init__(self):
        self.logger = logging.getLogger("AkamaiAdapter")

    def execute_request(self, data):
        self.logger.error("Akamai native API adapter is not implemented for this demo runtime")
        raise NotImplementedError(
            "Akamai requests must use adapterType=terraform-module in this demo. "
            "Update the claim/composition to route Akamai through the Terraform adapter."
        )
