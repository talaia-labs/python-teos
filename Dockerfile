FROM node:10.14.2
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
COPY ./tsconfig.json ./tsconfig.json
# build
RUN ["npm", "run", "build"]

# expose the startup port
EXPOSE 3000

# start the application
CMD ["npm", "run", "start-dev"]