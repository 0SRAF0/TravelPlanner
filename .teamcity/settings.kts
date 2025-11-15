import jetbrains.buildServer.configs.kotlin.*
import jetbrains.buildServer.configs.kotlin.buildFeatures.dockerRegistryConnections
import jetbrains.buildServer.configs.kotlin.buildFeatures.perfmon
import jetbrains.buildServer.configs.kotlin.buildSteps.SSHUpload
import jetbrains.buildServer.configs.kotlin.buildSteps.sshExec
import jetbrains.buildServer.configs.kotlin.buildSteps.sshUpload
import jetbrains.buildServer.configs.kotlin.projectFeatures.dockerRegistry
import jetbrains.buildServer.configs.kotlin.triggers.vcs
import jetbrains.buildServer.configs.kotlin.vcs.GitVcsRoot

/*
The settings script is an entry point for defining a TeamCity
project hierarchy. The script should contain a single call to the
project() function with a Project instance or an init function as
an argument.

VcsRoots, BuildTypes, Templates, and subprojects can be
registered inside the project using the vcsRoot(), buildType(),
template(), and subProject() methods respectively.

To debug settings scripts in command-line, run the

    mvnDebug org.jetbrains.teamcity:teamcity-configs-maven-plugin:generate

command and attach your debugger to the port 8000.

To debug in IntelliJ Idea, open the 'Maven Projects' tool window (View
-> Tool Windows -> Maven Projects), find the generate task node
(Plugins -> teamcity-configs -> teamcity-configs:generate), the
'Debug' option is available in the context menu for the task.
*/

version = "2025.07"

project {

    vcsRoot(GitGithubCom0sraf0TravelPlannerGitRefsHeadsMain1)

    buildType(BuildWeb)
    buildType(BuildApi)

    params {
        param("domain-name", "travelplanner.solutions")
        param("project-route", "/home/vpcuser/TravelPlaner")
        param("env.web", """
            ENVIRONMENT=deployment
            
            # Sys
            VITE_APP_API_BASE_URL=http://travelplanner.solutions:8060
            
            # Google Map
            VITE_GOOGLE_MAPS_API_KEY=AIzaSyDmyZ_sJw5q1fGztTGUbjcHQcrGPeccOa4
        """.trimIndent())
        param("env.api", """
            ENVIRONMENT=deployment
            
            # Sys
            SERVER_HOST=travelplanner.solutions
            SERVER_PORT=8060
            CORS_ORIGINS=http://travelplanner.solutions:3060
            
            # Google OAuth
            GOOGLE_CLIENT_ID=1058642267983-5ejpivgliqclab7afnq57eom20qgem63.apps.googleusercontent.com
            GOOGLE_CLIENT_SECRET=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
            GOOGLE_REDIRECT_URI=http://travelplanner.solutions:3060/auth/callback
            
            # Google AI
            GOOGLE_AI_API_KEY=AIzaSyDwixr4ZrCqAm0GDY141mrrHotL60XJfvQ
            
            # JWT
            JWT_SECRET=Frrli_WYdq-FahOQrk9Zei6INVzfnjJObJuoCmSBEgA
            JWT_ALGORITHM=HS256
            JWT_EXPIRATION_HOURS=24
            
            # MongoDB
            MONGODB_URI=mongodb+srv://root:mRaGrBX18gI8Osmj@travelplanner.70jvxlw.mongodb.net/?appName=TravelPlanner
        """.trimIndent())
        param("username", "")
    }

    features {
        dockerRegistry {
            id = "PROJECT_EXT_2"
            name = "Docker Registry"
            userName = "0sethmccarthy0"
            password = "credentialsJSON:2f031eb5-503b-46bf-a795-ed837567ac74"
        }
    }
}

object BuildApi : BuildType({
    name = "Build-API"

    params {
        param("env.prod", """
            ENVIRONMENT=deployment
            
            # Sys
            SERVER_HOST=travelplanner.solutions
            SERVER_PORT=8060
            CORS_ORIGINS=http://travelplanner.solutions:3060
            
            # Google OAuth
            GOOGLE_CLIENT_ID=1058642267983-5ejpivgliqclab7afnq57eom20qgem63.apps.googleusercontent.com
            GOOGLE_CLIENT_SECRET=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
            GOOGLE_REDIRECT_URI=http://travelplanner.solutions:3060/auth/callback
            
            # Google AI
            GOOGLE_AI_API_KEY=AIzaSyDwixr4ZrCqAm0GDY141mrrHotL60XJfvQ
            
            # JWT
            JWT_SECRET=Frrli_WYdq-FahOQrk9Zei6INVzfnjJObJuoCmSBEgA
            JWT_ALGORITHM=HS256
            JWT_EXPIRATION_HOURS=24
            
            # MongoDB
            MONGODB_URI=mongodb+srv://root:mRaGrBX18gI8Osmj@travelplanner.70jvxlw.mongodb.net/?appName=TravelPlanner
        """.trimIndent())
    }

    vcs {
        root(DslContext.settingsRoot)
    }

    steps {
        sshExec {
            name = "Clear Legacy Deployment"
            id = "Clear_Legacy_Deployment"
            commands = """
                cd %project_route%
                rm -rf backend
            """.trimIndent()
            targetUrl = "%api-domain_name%:%project_route%/backend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshUpload {
            name = "Transfer to the Remote Server"
            id = "Transfer_to_the_Remote_Server"
            transportProtocol = SSHUpload.TransportProtocol.SCP
            sourcePath = "backend/"
            targetUrl = "%api-domain_name%:%project_route%/backend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Create .env.prod"
            id = "Create_env_prod"
            commands = """
                cd %project_route%/backend
                cat <<'EOF' > .env.prod
                %env.prod%
                EOF
            """.trimIndent()
            targetUrl = "%api-domain_name%:%project_route%/backend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Docker Compose"
            id = "Docker_Compose"
            commands = """
                cd %project_route%/backend
                sudo docker compose --env-file .env.prod -f docker-compose-prod.yml up --build -d
            """.trimIndent()
            targetUrl = "%api-domain_name%:%project_route%/backend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
    }

    triggers {
        vcs {
        }
    }

    features {
        perfmon {
        }
        dockerRegistryConnections {
            loginToRegistry = on {
                dockerRegistryId = "PROJECT_EXT_2"
            }
        }
    }
})

object BuildWeb : BuildType({
    name = "Build-Web"

    params {
        param("env.prod", """
            ENVIRONMENT=deployment
            
            # Sys
            VITE_APP_API_BASE_URL=http://travelplanner.solutions:8060
            
            # Google Map
            VITE_GOOGLE_MAPS_API_KEY=AIzaSyDmyZ_sJw5q1fGztTGUbjcHQcrGPeccOa4
        """.trimIndent())
    }

    vcs {
        root(GitGithubCom0sraf0TravelPlannerGitRefsHeadsMain1)
    }

    steps {
        sshExec {
            name = "Clear Legacy Deployment"
            id = "Clear_Legacy_Deployment"
            commands = """
                cd %project_route%
                rm -rf frontend
            """.trimIndent()
            targetUrl = "%api-domain_name%:%project_route%/frontend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshUpload {
            name = "Transfer to the Remote Server"
            id = "Transfer_to_the_Remote_Server"
            transportProtocol = SSHUpload.TransportProtocol.SCP
            sourcePath = "frontend/"
            targetUrl = "%api-domain_name%:%project_route%/frontend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Create .env.prod"
            id = "Create_env_prod"
            commands = """
                cd %project_route%/backend
                cat <<'EOF' > .env.prod
                %env.prod%
                EOF
            """.trimIndent()
            targetUrl = "%api-domain_name%:%project_route%/frontend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
        sshExec {
            name = "Docker Compose"
            id = "Docker_Compose"
            commands = """
                cd %project_route%/frontend
                sudo docker compose --env-file .env.prod -f docker-compose-prod.yml up --build -d
            """.trimIndent()
            targetUrl = "%api-domain_name%:%project_route%/frontend"
            authMethod = uploadedKey {
                username = "vpcuser"
                key = "travelplaner-ibmc-vpc.prv"
            }
        }
    }

    triggers {
        vcs {
        }
    }

    features {
        perfmon {
        }
    }
})

object GitGithubCom0sraf0TravelPlannerGitRefsHeadsMain1 : GitVcsRoot({
    name = "git@github.com:0SRAF0/TravelPlanner.git#refs/heads/main (1)"
    url = "git@github.com:0SRAF0/TravelPlanner.git"
    branch = "refs/heads/main"
    branchSpec = "refs/heads/*"
    authMethod = uploadedKey {
        uploadedKey = "seth"
        passphrase = "credentialsJSON:e325be5f-9914-49c1-b84c-4aa2b81d8987"
    }
})
