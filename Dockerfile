FROM node:10.14.2 as builder
# set a location
WORKDIR /usr/pisa

# also copy the build artifacts from the statechannels folder
COPY ./statechannels/build ./statechannels/build

# copy the package files
COPY package*.json ./
# install packages
RUN ["npm", "ci"];
# copy the src and the tsconfig
COPY ./src ./src
COPY ./config.json ./config.json
COPY ./tsconfig.json ./tsconfig.json
# build
RUN ["npm", "run", "build"]


# start a new stage, we dont need to carry over all the unused precompiled code and dev dependencies
FROM node:10.14.2
WORKDIR /usr/pisa
# copy packages
COPY package*.json ./
COPY ./config.json ./config.json
COPY ./statechannels/build ./statechannels/build
# install production dependencies
RUN ["npm", "ci", "--only=prod"];


# copy the source code from the builder
COPY --from=builder ./usr/pisa/build ./build


# expose the startup port
EXPOSE 3000
# start the application
CMD ["npm", "run", "start"]