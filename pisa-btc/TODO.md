- Check all the interactions with core, figure out the edge cases and error codes
i.e: The justice transaction can already be in the blockchain the first time we push it
- Handle reconnection with ZMQ in case of broken pipe. The current version of the code fails if it does happen
